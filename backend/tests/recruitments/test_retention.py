"""招聘留存的精确边界、聚合兼容、文件重试和并发回归。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connections, close_old_connections
from django.test import override_settings

from apps.accounts.cancellation import cancel_account
from apps.applications.services import submit_application
from apps.applications.models import Application, ApplicationStatusHistory, ResumeRemoval
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.audit.service import record
from apps.core import clock
from apps.core.choices import ApplicationStatus
from apps.core.errors import NotAuthenticated
from apps.notifications.models import EmailLog, Notification
from apps.recruitments.retention import purge_expired_applications
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class RetentionTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.now = clock.now()
        self.end = self.now - timedelta(days=180)
        self.owner, self.user = make_user(), make_user()
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.enterContext(override_settings(PRIVATE_FILE_ROOT=self.root))

    def test_first_of_three_times_and_delayed_cleanup(self):
        for first in ("closed_at", "full_at", "deleted_at"):
            times = {field: self.end + timedelta(days=1) for field in ("closed_at", "full_at", "deleted_at")}
            times[first] = self.end
            job = make_recruitment(self.owner, status="full", close_reason="manual", **times)
            app = make_application(job, self.user, status="invalid")
            notice = Notification.objects.create(recipient=self.user, application=app, recruitment=job,
                                                 type="recruitment_deleted", title="招聘删除", content="已失效")
            EmailLog.objects.create(notification=notice, to_email=self.user.email)
            ApplicationStatusHistory.objects.create(application=app, recruitment=job, from_status="accepted",
                    to_status="invalid", reason="delete_invalid", actor=self.owner, occurred_at=self.end)
            log = record(actor=self.user, action=actions.APPLICATION_UPDATE, target_type="application",
                         target_id=app.pk, reason="保留原因")
            self.client.force_authenticate(self.owner)
            before = self.now - timedelta(microseconds=1)
            with self.freeze_at(before):
                self.assertEqual(self.client.get(f"/api/v1/applications/{app.pk}").status_code, 200)
                self.assertFalse(purge_expired_applications(job.pk, now=before))
            with self.freeze_at(self.now):
                self.assertEqual(self.client.get(f"/api/v1/users/{self.user.uid}", {"application_id": app.pk}).status_code, 404)
                self.assertEqual(self.client.get(f"/api/v1/applications/{app.pk}").status_code, 404)
                self.assertTrue(purge_expired_applications(job.pk))
                self.assertFalse(purge_expired_applications(job.pk))
            job.refresh_from_db()
            self.assertEqual(job.application_status_counts, dict.fromkeys(ApplicationStatus.values, 0) | {"invalid": 1})
            self.assertFalse(Application.objects.filter(pk=app.pk).exists())
            self.assertFalse(Notification.objects.filter(pk=notice.pk).exists())
            self.assertFalse(EmailLog.objects.filter(notification_id=notice.pk).exists())
            self.assertFalse(ApplicationStatusHistory.objects.filter(application_id=app.pk).exists())
            log.refresh_from_db()
            self.assertEqual((log.actor_id, log.target_id, log.reason, log.actor_role), (None, app.pk, "保留原因", "student"))
            self.assertIsNotNone(log.actor_ref)

    def test_pending_file_retry_and_transaction_rollback(self):
        job = make_recruitment(self.owner, deadline=self.end)
        app = make_application(job, self.user)
        path = self.root / app.resume_file.name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"%PDF-fixture")
        with patch("apps.recruitments.retention.erase_notifications", side_effect=RuntimeError("回滚检查")):
            with self.assertRaises(RuntimeError):
                purge_expired_applications(job.pk, now=self.now)
        self.assertTrue(path.exists())
        self.assertTrue(Application.objects.filter(pk=app.pk).exists())
        self.assertFalse(ResumeRemoval.objects.exists())
        with patch("apps.recruitments.retention.discard_resume", return_value=False):
            self.assertTrue(purge_expired_applications(job.pk, now=self.now))
        job.refresh_from_db()
        self.assertEqual((job.closed_at, job.application_status_counts["rejected"]), (self.end, 1))
        self.assertTrue(ResumeRemoval.objects.filter(path=app.resume_file.name).exists())
        call_command("run_purge_applications", stdout=StringIO())
        call_command("run_purge_applications", stdout=StringIO())
        self.assertFalse(path.exists())
        self.assertFalse(ResumeRemoval.objects.exists())

    def test_deleted_job_uses_first_recorded_end_not_an_unapplied_deadline(self):
        job = make_recruitment(self.owner, deleted_at=self.now, deadline=self.end - timedelta(days=30))
        app = make_application(job, self.user, status="invalid")
        with self.freeze_at(self.now):
            self.client.force_authenticate(self.user)
            self.assertEqual(self.client.get(f"/api/v1/applications/{app.pk}").status_code, 200)
            self.assertFalse(purge_expired_applications(job.pk))
        self.assertTrue(purge_expired_applications(job.pk, now=self.now + timedelta(days=180)))

    def test_existing_final_snapshot_is_authoritative(self):
        counts = dict.fromkeys(ApplicationStatus.values, 0) | {"accepted": 3}
        job = make_recruitment(self.owner, status="closed", closed_at=self.end, close_reason="manual",
                               application_status_counts=counts, applications_anonymized_at=self.now)
        make_application(job, self.user, status="accepted")
        legacy = Notification.objects.create(recipient=self.owner, recruitment=job, type="application_submitted",
                                             title="旧通知", content="收到申请")
        call_command("run_purge_applications", stdout=StringIO())
        job.refresh_from_db()
        self.assertEqual(job.application_status_counts, counts)
        self.assertFalse(Notification.objects.filter(pk=legacy.pk).exists())
        self.assertFalse(job.applications.exists())

    def race(self, *operations):
        gate = Barrier(len(operations))

        def run(function):
            close_old_connections()
            try:
                gate.wait(timeout=8)
                return function()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            tasks = [pool.submit(run, fn) for fn in operations]
            return [task.result(timeout=15) for task in tasks]

    def test_submission_racing_cancellation_leaves_no_private_record(self):
        job = make_recruitment(self.owner)

        def submit():
            resume = SimpleUploadedFile("resume.pdf", b"%PDF-1.7\nfixture\n%%EOF", content_type="application/pdf")
            try:
                submit_application(self.user, job.pk, resume=resume)
                return True
            except NotAuthenticated:
                return False

        written, _ = self.race(submit, lambda: cancel_account(self.user))
        job.refresh_from_db()
        self.assertEqual(job.anonymous_counts.get("withdrawn", 0), int(written))
        self.assertFalse(job.applications.exists())
        self.assertFalse(list(self.root.rglob("*.pdf")))

    def test_completed_legacy_snapshot_cannot_take_new_applications(self):
        job = make_recruitment(self.owner, applications_anonymized_at=self.now,
                               application_status_counts=dict.fromkeys(ApplicationStatus.values, 0))
        self.client.force_authenticate(self.user)
        detail = self.client.get(f"/api/v1/recruitments/{job.pk}").data["data"]
        self.assertFalse(detail["permissions"]["can_apply"])
        file = SimpleUploadedFile("profile.pdf", b"%PDF-1.7\nfixture", content_type="application/pdf")
        denied = self.client.post(f"/api/v1/recruitments/{job.pk}/applications", {"resume": file}, format="multipart")
        self.assertEqual(denied.status_code, 409)
        self.assertFalse(job.applications.exists())

    def test_concurrent_purge_and_cancellation_count_once(self):
        job = make_recruitment(self.owner, accepted_count=1, max_headcount=1, full_at=self.end, status="full")
        make_application(job, self.user, status="accepted")
        self.race(lambda: purge_expired_applications(job.pk), lambda: cancel_account(self.user))
        job.refresh_from_db()
        self.assertEqual((job.accepted_count, job.application_status_counts["accepted"]), (1, 1))
        self.assertFalse(job.applications.exists())
