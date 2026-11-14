"""业务事件、站内通知与个人申请状态的事务一致性回归。"""
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connections
from django.test import override_settings

from apps.announcements import services as announcements
from apps.applications import services as applications
from apps.applications.models import Application, ApplicationStatusHistory
from apps.audit.models import AuditLog
from apps.core import clock
from apps.core.errors import BizError
from apps.notifications import types
from apps.notifications.models import EmailLog, Notification
from apps.notifications.service import notify
from apps.recruitments import services as recruitments, state
from apps.recruitments.models import RecruitmentTag
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_tag, make_user


class EventConsistencyTest(TxTestCase):
    def setUp(self):
        super().setUp()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        override = override_settings(PRIVATE_FILE_ROOT=Path(temp.name))
        override.enable()
        self.addCleanup(override.disable)
        self.owner, self.applicant = make_user(), make_user()
        self.admin = make_user(is_admin=True)
        self.r = make_recruitment(self.owner)

    def submit(self, user=None, recruitment=None):
        return applications.submit_application(
            user or self.applicant, (recruitment or self.r).pk,
            resume=SimpleUploadedFile("resume.pdf", b"%PDF-1.7\nsynthetic resume", content_type="application/pdf"),
        )

    def notices(self):
        return list(Notification.objects.order_by("pk").values_list("type", "recipient_id", "application_id"))

    def assert_no_email(self):
        self.assertFalse(EmailLog.objects.exists())

    def parallel(self, jobs):
        gate = Barrier(len(jobs))

        def run(job):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                return job()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return [future.result(timeout=20) for future in futures]

    def test_submit_modify_withdraw_and_reapply_notify_publisher_with_correct_record(self):
        first = self.submit()
        modified = applications.modify_application(self.applicant, first.pk, note="修改说明", update_note=True)
        applications.modify_application(self.applicant, first.pk, note="修改说明", update_note=True)
        applications.perform_application_action(self.owner, first.pk, "hold")
        applications.perform_application_action(self.owner, first.pk, "unhold")
        applications.perform_application_action(self.applicant, first.pk, "withdraw")
        with self.assertRaises(BizError):
            applications.perform_application_action(self.applicant, first.pk, "withdraw")
        second = self.submit()
        self.assertNotEqual(first.pk, second.pk)
        self.assertTrue(modified.has_unseen_update)
        self.assertEqual(self.notices(), [
            (types.APPLICATION_SUBMITTED, self.owner.pk, first.pk),
            (types.APPLICATION_UPDATED, self.owner.pk, first.pk),
            (types.APPLICATION_WITHDRAWN, self.owner.pk, first.pk),
            (types.APPLICATION_SUBMITTED, self.owner.pk, second.pk),
        ])
        self.assert_no_email()

    def test_manual_decisions_notify_only_the_applicant_once_and_explain_rejection(self):
        accepted = make_application(self.r, self.applicant)
        rejected = make_application(self.r, make_user())
        for app, action in ((accepted, "accept"), (rejected, "reject")):
            applications.perform_application_action(self.owner, app.pk, action)
            with self.assertRaises(BizError):
                applications.perform_application_action(self.owner, app.pk, action)
        self.assertEqual(self.notices(), [
            (types.APPLICATION_ACCEPTED, accepted.applicant_id, accepted.pk),
            (types.APPLICATION_REJECTED, rejected.applicant_id, rejected.pk),
        ])
        self.assertIn("发布者主动拒绝", Notification.objects.get(type=types.APPLICATION_REJECTED).content)
        self.assertEqual(ApplicationStatusHistory.objects.count(), 2)
        self.assert_no_email()

    def test_recruitment_update_only_notifies_active_applicants_before_full_transition(self):
        accepted = make_application(self.r, self.applicant)
        pending = make_application(self.r, make_user())
        make_application(self.r, make_user(), status="rejected")
        make_application(self.r, pending.applicant, status="withdrawn")
        applications.perform_application_action(self.owner, accepted.pk, "accept")
        start = Notification.objects.latest("pk").pk
        recruitments.update_recruitment(self.owner, self.r.pk, data={"max_headcount": 1})
        self.assertEqual(self.notices()[1:], [
            (types.RECRUITMENT_UPDATED, accepted.applicant_id, accepted.pk),
            (types.RECRUITMENT_UPDATED, pending.applicant_id, pending.pk),
            (types.APPLICATION_REJECTED, pending.applicant_id, pending.pk),
        ])
        self.assertIn("招聘已满员", Notification.objects.get(pk__gt=start, type=types.APPLICATION_REJECTED).content)
        state.sync_recruitment(self.r.pk)
        self.assertEqual(Notification.objects.count(), 4)
        self.assert_no_email()

    def test_unchanged_recruitment_content_and_tag_order_do_not_create_update_events(self):
        make_application(self.r, self.applicant)
        first, second = make_tag(), make_tag()
        RecruitmentTag.objects.bulk_create([RecruitmentTag(recruitment=self.r, tag=tag) for tag in (first, second)])
        version = self.r.updated_at
        recruitments.update_recruitment(self.owner, self.r.pk, data={"title": self.r.title, "tag_ids": [second.pk, first.pk]})
        self.r.refresh_from_db()
        self.assertEqual(self.r.updated_at, version)
        self.assertFalse(Notification.objects.exists())
        recruitments.update_recruitment(self.owner, self.r.pk, data={"tag_ids": [second.pk]})
        self.assertEqual(self.notices(), [(types.RECRUITMENT_UPDATED, self.applicant.pk, Application.objects.get().pk)])

    def test_governance_deletion_notifies_only_invalidated_applicants_and_publisher(self):
        accepted = make_application(self.r, self.applicant)
        pending = make_application(self.r, make_user())
        rejected = make_application(self.r, make_user(), status="rejected")
        withdrawn = make_application(self.r, make_user(), status="withdrawn")
        applications.perform_application_action(self.owner, accepted.pk, "accept")
        accepted.refresh_from_db()
        first_decision = accepted.decided_at
        recruitments.governance_delete_recruitment(self.admin, self.r.pk, reason="违规内容")
        with self.assertRaises(BizError):
            recruitments.governance_delete_recruitment(self.admin, self.r.pk, reason="重复处理")
        self.assertEqual(self.notices()[1:], [
            (types.RECRUITMENT_DELETED, accepted.applicant_id, accepted.pk),
            (types.RECRUITMENT_DELETED, pending.applicant_id, pending.pk),
            (types.ADMIN_REMOVED, self.owner.pk, None),
        ])
        self.assertIn("违规内容", Notification.objects.get(type=types.ADMIN_REMOVED).content)
        for notice in Notification.objects.filter(type=types.RECRUITMENT_DELETED):
            self.assertIn("申请已失效", notice.content)
        accepted.refresh_from_db(); rejected.refresh_from_db(); withdrawn.refresh_from_db()
        self.assertEqual((accepted.status, accepted.decided_at), ("invalid", first_decision))
        self.assertEqual((rejected.status, withdrawn.status), ("rejected", "withdrawn"))
        self.assert_no_email()

    def test_delayed_timeout_notifies_once_with_effective_decision_time(self):
        deadline = clock.now() - timedelta(days=730)
        self.r.deadline = deadline
        self.r.save(update_fields=["deadline"])
        app = make_application(self.r, self.applicant)
        before = clock.now()
        state.sync_recruitment(self.r.pk)
        state.sync_recruitment(self.r.pk)
        app.refresh_from_db()
        self.assertEqual((app.status, app.decided_at), ("rejected", deadline + timedelta(days=7)))
        notice = Notification.objects.get(type=types.APPLICATION_REJECTED)
        self.assertGreaterEqual(notice.created_at, before)
        self.assertIn("七天处理期已结束", notice.content)
        self.assertEqual(self.notices(), [
            (types.RECRUITMENT_CLOSED, self.owner.pk, None),
            (types.APPLICATION_REJECTED, self.applicant.pk, app.pk),
        ])
        self.client.force_authenticate(self.applicant)
        row = self.client.get("/api/v1/me/applications?status=rejected").data["data"]["items"][0]
        self.assertEqual(row["id"], app.pk)
        self.assertFalse(row["permissions"]["can_modify"])
        self.assert_no_email()

    def test_late_full_and_concurrent_sync_generate_one_result(self):
        full_at = clock.now() - timedelta(days=730)
        self.r.status, self.r.max_headcount, self.r.accepted_count = "full", 1, 1
        self.r.full_at = full_at
        self.r.save(update_fields=["status", "max_headcount", "accepted_count", "full_at"])
        make_application(self.r, make_user(), status="accepted", decided_at=full_at)
        app = make_application(self.r, self.applicant)
        self.parallel([lambda: state.sync_recruitment(self.r.pk)] * 2)
        app.refresh_from_db()
        self.assertEqual((app.status, app.decided_at), ("rejected", full_at))
        self.assertEqual(self.notices(), [(types.APPLICATION_REJECTED, self.applicant.pk, app.pk)])
        self.assertEqual(ApplicationStatusHistory.objects.count(), 1)
        self.assertIn("招聘已满员", Notification.objects.get().content)
        self.assert_no_email()

    def test_concurrent_identical_edits_create_one_event_for_each_actual_change(self):
        app = make_application(self.r, self.applicant)
        self.parallel([lambda: applications.modify_application(self.applicant, app.pk, note="同一版本", update_note=True)] * 2)
        self.parallel([lambda: recruitments.update_recruitment(self.owner, self.r.pk, data={"description": "同一描述"})] * 2)
        self.assertEqual(self.notices(), [
            (types.APPLICATION_UPDATED, self.owner.pk, app.pk),
            (types.RECRUITMENT_UPDATED, self.applicant.pk, app.pk),
        ])
        self.assertEqual(AuditLog.objects.filter(action="application_update").count(), 1)
        self.assert_no_email()

    def test_noop_application_edit_keeps_acknowledgement_and_content_version(self):
        app = make_application(self.r, self.applicant, note="原说明", has_unseen_update=False)
        version = app.updated_at
        applications.modify_application(self.applicant, app.pk, note="原说明", update_note=True)
        app.refresh_from_db()
        self.assertFalse(app.has_unseen_update)
        self.assertEqual(app.updated_at, version)
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(AuditLog.objects.exists())

    def test_my_application_states_keep_history_permissions_and_publisher_marks(self):
        expected = {}
        for status in ("processing", "accepted", "rejected", "withdrawn", "invalid"):
            recruitment = make_recruitment(self.owner)
            app = self.submit(recruitment=recruitment)
            if status in {"accepted", "invalid"}:
                applications.perform_application_action(self.owner, app.pk, "accept")
            elif status == "rejected":
                applications.perform_application_action(self.owner, app.pk, "reject")
            elif status == "withdrawn":
                applications.perform_application_action(self.applicant, app.pk, "withdraw")
            if status == "invalid":
                app.refresh_from_db()
                first_decision = app.decided_at
                recruitments.delete_recruitment(self.owner, recruitment.pk)
            if status == "processing":
                applications.modify_application(self.applicant, app.pk, note="更新说明", update_note=True)
                applications.perform_application_action(self.owner, app.pk, "hold")
            expected[status] = app
        self.client.force_authenticate(self.applicant)
        listing = self.client.get("/api/v1/me/applications").data["data"]
        self.assertEqual(listing["total"], 5)
        for status, app in expected.items():
            row = self.client.get(f"/api/v1/me/applications?status={status}").data["data"]["items"][0]
            self.assertEqual((row["id"], row["status"]), (app.pk, status))
            self.assertNotIn("publisher_mark", row)
            self.assertNotIn("has_unseen_update", row)
            self.assertTrue(row["permissions"]["can_download_resume"])
            self.assertEqual(row["permissions"]["can_modify"], status == "processing")
            self.assertEqual(row["recruitment"]["is_deleted"], status == "invalid")
            download = self.client.get(f"/api/v1/applications/{app.pk}/resume")
            self.assertEqual(download.status_code, 200)
            download.close()
        expected["invalid"].refresh_from_db()
        self.assertEqual(expected["invalid"].decided_at, first_decision)
        self.client.force_authenticate(self.owner)
        app = expected["processing"]
        row = self.client.get(f"/api/v1/recruitments/{app.recruitment_id}/applications").data["data"]["items"][0]
        self.assertEqual(row["publisher_mark"], "hold")
        self.assertTrue(row["has_unseen_update"])
        self.assertEqual(self.client.get(f'/api/v1/applications/{expected["invalid"].pk}/resume').status_code, 403)

    def test_announcement_governance_keeps_author_notice_after_role_revocation(self):
        author = make_user(is_admin=True)
        announcement = announcements.create_announcement(actor=author, title="竞赛", content="正文",
                                                        time_kind="event", event_at=clock.now())
        announcements.update_announcement(announcement.pk, actor=author, content="更新正文")
        self.assertFalse(Notification.objects.exists())
        author.is_admin = False
        author.save(update_fields=["is_admin"])
        announcements.governance_delete_announcement(announcement.pk, actor=self.admin, reason="已失效")
        with self.assertRaises(BizError):
            announcements.governance_delete_announcement(announcement.pk, actor=self.admin, reason="重复治理")
        notice = Notification.objects.get()
        self.assertEqual((notice.recipient_id, notice.announcement_id, notice.recruitment_id, notice.application_id),
                         (author.pk, announcement.pk, None, None))
        self.assertIn("竞赛", notice.content)
        self.assertIn("已失效", notice.content)
        self.client.force_authenticate(author)
        row = self.client.get("/api/v1/notifications").data["data"]["items"][0]
        self.assertTrue(row["target_is_deleted"])
        self.assert_no_email()

    def test_own_announcement_deletion_has_no_broadcast(self):
        announcement = announcements.create_announcement(actor=self.admin, title="竞赛", content="正文",
                                                        time_kind="event", event_at=clock.now())
        announcements.soft_delete_announcement(announcement.pk, actor=self.admin)
        self.assertFalse(Notification.objects.exists())
        self.assert_no_email()

    def test_failure_after_notification_insert_rolls_back_business_history_and_audit(self):
        app = make_application(self.r, self.applicant)

        def fail_after_insert(**kwargs):
            notify(**kwargs)
            raise RuntimeError("injected notification failure")

        with mock.patch("apps.applications.services.notify", side_effect=fail_after_insert), self.assertRaises(RuntimeError):
            applications.perform_application_action(self.owner, app.pk, "accept")
        app.refresh_from_db(); self.r.refresh_from_db()
        self.assertEqual((app.status, self.r.accepted_count), ("processing", 0))
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(ApplicationStatusHistory.objects.exists())
        self.assertFalse(AuditLog.objects.exists())
        self.assert_no_email()

    def test_announcement_notice_failure_rolls_back_deletion_and_its_audit(self):
        announcement = announcements.create_announcement(actor=self.admin, title="竞赛", content="正文",
                                                        time_kind="event", event_at=clock.now())
        audit_count = AuditLog.objects.count()

        def fail_after_insert(**kwargs):
            notify(**kwargs)
            raise RuntimeError("injected notification failure")

        with mock.patch("apps.announcements.services.notify", side_effect=fail_after_insert), self.assertRaises(RuntimeError):
            announcements.governance_delete_announcement(announcement.pk, actor=self.admin, reason="违规")
        announcement.refresh_from_db()
        self.assertIsNone(announcement.deleted_at)
        self.assertEqual(AuditLog.objects.count(), audit_count)
        self.assertFalse(Notification.objects.exists())
        self.assert_no_email()
