from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections
from django.test import override_settings

from apps.audit import actions
from apps.audit.models import AuditLog
from apps.applications.policies import resolve_application_access
from apps.applications.services import modify_application, perform_application_action
from apps.core import clock
from apps.core.choices import ApplicationStatus, PublisherMark, RecruitmentStatus
from apps.core.errors import BizError, ErrorCode
from apps.files.storage import discard_resume, open_resume, save_resume
from apps.notifications.models import Notification
from apps.notifications.types import (
    APPLICATION_ACCEPTED, APPLICATION_REJECTED, APPLICATION_UPDATED, APPLICATION_WITHDRAWN,
)
from apps.recruitments.models import Recruitment
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


def pdf_upload(name="resume.pdf", content=b"%PDF-1.7\nresume body"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class ApplicationServiceTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.now = clock.now()
        self.publisher = make_user()
        self.applicant = make_user()
        self.r = make_recruitment(self.publisher, max_headcount=3)
        self.app = make_application(self.r, self.applicant)

    def run_action(self, user, action, **kwargs):
        with self.freeze_at(self.now):
            return perform_application_action(user, self.app.pk, action, **kwargs)

    def test_accept_at_last_slot_rejects_remaining_applications_once(self):
        self.r.max_headcount = 1
        self.r.save(update_fields=["max_headcount"])
        other = make_application(self.r, make_user())

        self.run_action(self.publisher, "accept")

        self.r.refresh_from_db()
        self.app.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((self.r.status, self.r.accepted_count), (RecruitmentStatus.FULL, 1))
        self.assertEqual(self.app.status, ApplicationStatus.ACCEPTED)
        self.assertEqual(other.status, ApplicationStatus.REJECTED)
        self.assertEqual(
            list(Notification.objects.order_by("type").values_list("type", flat=True)),
            [APPLICATION_ACCEPTED, APPLICATION_REJECTED],
        )
        self.assertEqual(Notification.objects.filter(type=APPLICATION_REJECTED).count(), 1)
        self.assertEqual(
            list(AuditLog.objects.filter(action=actions.APPLICATION_UPDATE).values_list("target_id", flat=True)),
            [self.app.pk],
        )

    def test_concurrent_accepts_cannot_exceed_the_last_slot(self):
        if connection.vendor != "postgresql":
            self.skipTest("需要 PostgreSQL 行锁")
        self.r.max_headcount = 1
        self.r.save(update_fields=["max_headcount"])
        other = make_application(self.r, make_user())
        barrier = Barrier(2, timeout=10)

        def accept(application_id):
            connections.close_all()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                barrier.wait()
                try:
                    perform_application_action(self.publisher, application_id, "accept")
                    return "ok"
                except BizError as error:
                    return error.code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(accept, item.pk) for item in (self.app, other)]
            outcomes = [future.result(timeout=20) for future in futures]

        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count(ErrorCode.APPLICATION_NOT_PROCESSING), 1)
        self.r.refresh_from_db()
        self.app.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((self.r.status, self.r.accepted_count), (RecruitmentStatus.FULL, 1))
        self.assertEqual(
            {self.app.status, other.status},
            {ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED},
        )
        self.assertEqual(Notification.objects.filter(type=APPLICATION_ACCEPTED).count(), 1)
        self.assertEqual(Notification.objects.filter(type=APPLICATION_REJECTED).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action=actions.APPLICATION_UPDATE).count(), 1)

    def test_repeated_terminal_action_does_not_duplicate_notification_or_count(self):
        self.run_action(self.publisher, "reject")
        with self.freeze_at(self.now), self.assertRaises(BizError) as caught:
            perform_application_action(self.publisher, self.app.pk, "reject")

        self.assertEqual(caught.exception.code, ErrorCode.APPLICATION_NOT_PROCESSING)
        self.assertEqual(Notification.objects.filter(type=APPLICATION_REJECTED).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action=actions.APPLICATION_UPDATE).count(), 1)
        self.r.refresh_from_db()
        self.assertEqual(self.r.accepted_count, 0)

    def test_hold_and_unhold_are_private_and_idempotent(self):
        self.run_action(self.publisher, "hold")
        self.run_action(self.publisher, "hold")
        held = self.app
        held.refresh_from_db()
        self.assertEqual(held.publisher_mark, PublisherMark.HOLD)
        self.assertFalse(held.has_unseen_update)
        self.assertFalse(
            any(notification.type in {APPLICATION_ACCEPTED, APPLICATION_REJECTED}
                for notification in Notification.objects.all())
        )

        self.run_action(self.publisher, "unhold")
        self.run_action(self.publisher, "unhold")
        held.refresh_from_db()
        self.assertEqual(held.publisher_mark, PublisherMark.NONE)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(
            AuditLog.objects.filter(action=actions.APPLICATION_UPDATE, target_id=self.app.pk).count(),
            2,
        )

    def test_withdraw_closes_resume_access_and_sends_one_publisher_notice(self):
        self.run_action(self.applicant, "withdraw")

        self.app.refresh_from_db()
        self.assertEqual(self.app.status, ApplicationStatus.WITHDRAWN)
        access = resolve_application_access(self.applicant, self.app, self.r, self.now)
        self.assertFalse(access.can_download_resume)
        self.assertEqual(
            list(Notification.objects.values_list("recipient_id", "type")),
            [(self.publisher.pk, APPLICATION_WITHDRAWN)],
        )
        self.assertEqual(
            AuditLog.objects.filter(action=actions.APPLICATION_UPDATE, target_id=self.app.pk).count(),
            1,
        )

    def test_wrong_actor_cannot_process_or_withdraw(self):
        stranger = make_user()
        for user, action, expected_code in (
            (stranger, "accept", ErrorCode.NOT_FOUND),
            (self.publisher, "withdraw", ErrorCode.FORBIDDEN),
        ):
            with self.subTest(action=action), self.freeze_at(self.now), self.assertRaises(BizError) as caught:
                perform_application_action(user, self.app.pk, action)
            self.assertEqual(caught.exception.code, expected_code)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, ApplicationStatus.PROCESSING)
        self.assertEqual(Notification.objects.count(), 0)

    def test_accept_and_withdraw_compete_under_the_same_recruitment_lock(self):
        if connection.vendor != "postgresql":
            self.skipTest("需要 PostgreSQL 行锁")
        self.r.max_headcount = 1
        self.r.save(update_fields=["max_headcount"])
        barrier = Barrier(2, timeout=10)

        def act(user, action):
            connections.close_all()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                barrier.wait()
                try:
                    perform_application_action(user, self.app.pk, action)
                    return "ok"
                except BizError as error:
                    return error.code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                pool.submit(act, self.publisher, "accept"),
                pool.submit(act, self.applicant, "withdraw"),
            ]
            outcomes = [future.result(timeout=20) for future in results]

        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count(ErrorCode.APPLICATION_NOT_PROCESSING), 1)
        self.r.refresh_from_db()
        self.app.refresh_from_db()
        if self.app.status == ApplicationStatus.ACCEPTED:
            self.assertEqual(self.r.accepted_count, 1)
        else:
            self.assertEqual((self.r.accepted_count, self.app.status), (0, ApplicationStatus.WITHDRAWN))

    def test_modification_read_version_does_not_clear_newer_update(self):
        with self.freeze_at(self.now):
            first = modify_application(self.applicant, self.app.pk, note="第一版", update_note=True)
        first_version = first.updated_at
        with self.freeze_at(self.now + timedelta(seconds=1)):
            second = modify_application(self.applicant, self.app.pk, note="第二版", update_note=True)
        second_version = second.updated_at
        self.assertTrue(second.has_unseen_update)

        with self.freeze_at(self.now + timedelta(seconds=2)):
            stale = perform_application_action(
                self.publisher, self.app.pk, "read", seen_updated_at=first_version,
            )
        self.assertTrue(stale.has_unseen_update)

        with self.freeze_at(self.now + timedelta(seconds=3)):
            current = perform_application_action(
                self.publisher, self.app.pk, "read", seen_updated_at=second_version,
            )
        self.assertFalse(current.has_unseen_update)
        self.assertEqual(current.updated_at, second_version)
        self.assertEqual(Notification.objects.filter(type=APPLICATION_UPDATED).count(), 2)
        self.assertEqual(
            AuditLog.objects.filter(action=actions.APPLICATION_UPDATE, target_id=self.app.pk).count(),
            2,
        )

    def test_resume_replacement_cleans_old_file_only_after_commit(self):
        with override_settings(PRIVATE_FILE_ROOT=Path(settings.PRIVATE_FILE_ROOT) / "replacement-test"):
            old = save_resume(pdf_upload("old.pdf", b"%PDF-1.7\nold"))
            self.app.resume_file = old.path
            self.app.save(update_fields=["resume_file"])
            with self.freeze_at(self.now):
                updated = modify_application(
                    self.applicant, self.app.pk, resume=pdf_upload("new.pdf", b"%PDF-1.7\nnew"),
                )

            self.assertEqual(updated.resume_name, "new.pdf")
            self.assertFalse(Path(settings.PRIVATE_FILE_ROOT, old.path).exists())
            with open_resume(updated.resume_file.name) as stream:
                self.assertEqual(stream.read(), b"%PDF-1.7\nnew")
            discard_resume(updated.resume_file.name)

    def test_failed_resume_replacement_keeps_old_file_and_removes_new_file(self):
        root = Path(settings.PRIVATE_FILE_ROOT) / "replacement-failure-test"
        with override_settings(PRIVATE_FILE_ROOT=root):
            old = save_resume(pdf_upload("old.pdf", b"%PDF-1.7\nold"))
            self.app.resume_file = old.path
            self.app.save(update_fields=["resume_file"])
            with mock.patch("apps.applications.services.notify", side_effect=RuntimeError("notify failed")):
                with self.freeze_at(self.now), self.assertRaisesMessage(RuntimeError, "notify failed"):
                    modify_application(
                        self.applicant, self.app.pk, resume=pdf_upload("new.pdf", b"%PDF-1.7\nnew"),
                    )

            self.app.refresh_from_db()
            self.assertEqual(self.app.resume_file.name, old.path)
            self.assertFalse(AuditLog.objects.filter(action=actions.APPLICATION_UPDATE).exists())
            with open_resume(old.path) as stream:
                self.assertEqual(stream.read(), b"%PDF-1.7\nold")
            files = [path for path in (root / "resumes").rglob("*") if path.is_file()]
            self.assertEqual(len(files), 1)
            discard_resume(old.path)

    def test_processing_window_end_syncs_before_action(self):
        Recruitment.objects.filter(pk=self.r.pk).update(
            status=RecruitmentStatus.CLOSED,
            closed_at=self.now - timedelta(days=7),
            close_reason="manual",
        )
        with self.freeze_at(self.now), self.assertRaises(BizError) as caught:
            perform_application_action(self.publisher, self.app.pk, "accept")

        self.assertEqual(caught.exception.code, ErrorCode.APPLICATION_NOT_PROCESSING)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, ApplicationStatus.REJECTED)
