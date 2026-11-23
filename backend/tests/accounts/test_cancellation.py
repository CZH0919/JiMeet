"""账号注销、跨设备失效和新账号隔离。"""
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.cancellation import cancel_account
from apps.accounts.models import RegistrationVerification, User
from apps.announcements.models import Announcement, AnnouncementSubmission
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.chat.models import ChatConversation, ChatMessage
from apps.core import clock
from apps.notifications.models import Notification
from apps.recruitments.retention import purge_expired_applications
from apps.recruitments.services import governance_delete_recruitment
from tests.accounts.test_auth import CsrfFlowClient, VALID, REGISTER_URL
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class CancellationTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user(email=VALID["email"], is_admin=True, role="teacher", password=VALID["password"])
        self.other = make_user()
        self.client.force_login(self.user)

    def test_confirm_csrf_sessions_old_proofs_and_independent_reregistration(self):
        second = APIClient()
        second.force_login(self.user)
        secure = APIClient(enforce_csrf_checks=True)
        secure.force_login(self.user)
        url = "/api/v1/me"
        self.assertEqual(APIClient().delete(url, {"confirm": True}, format="json").status_code, 401)
        self.assertEqual(secure.delete(url, {"confirm": True}, format="json").status_code, 403)
        for invalid in ({}, {"confirm": False}, {"confirm": "true"}, {"confirm": True, "uid": self.other.uid}):
            self.assertEqual(self.client.delete(url, invalid, format="json").status_code, 400)
        browser = CsrfFlowClient()
        browser.verify_email(self.user.email)
        login_browser = CsrfFlowClient()
        with self.freeze_at(clock.now() + timedelta(minutes=2)):
            old_code = login_browser.delivered_code(self.user.email, purpose="login")
        old_uid, old_email = self.user.uid, self.user.email
        token = secure.get("/api/v1/auth/csrf").data["data"]["csrf_token"]
        response = secure.delete(url, {"confirm": True}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual((response.status_code, response.data["data"]), (200, None))
        self.assertEqual(second.get(url).status_code, 401)
        self.assertEqual(secure.get(url).status_code, 401)
        self.assertFalse(RegistrationVerification.objects.exists())
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.uid, old_uid)
        self.assertFalse(self.user.is_active or self.user.is_admin or self.user.has_usable_password())
        self.assertFalse(User.objects.filter(email=old_email).exists())
        self.assertIsNone(self.user.public_uid)
        self.assertEqual(browser.post_json(REGISTER_URL, VALID).status_code, 400)
        browser.verify_email(old_email)
        response = browser.post_json(REGISTER_URL, VALID)
        self.assertEqual(response.status_code, 201)
        new = User.objects.get(email=old_email)
        self.assertNotIn(new.uid, (old_uid, self.user.uid))
        self.assertFalse(new.is_admin)
        self.assertEqual(browser.get("/api/v1/me/applications").data["data"]["total"], 0)
        self.assertEqual(secure.get(url).status_code, 401)
        self.assertEqual(login_browser.post_json("/api/v1/auth/login", {"email": old_email, "code": old_code}).status_code, 400)
        audit = AuditLog.objects.get(action=actions.ACCOUNT_CANCEL)
        self.assertIsNone(audit.actor_id)
        self.assertIsNotNone(audit.actor_ref)
        self.assertEqual((audit.actor_role, audit.actor_is_admin, audit.target_id), ("teacher", True, self.user.pk))

    def test_verified_grant_issued_before_another_session_created_account_is_revoked(self):
        email = "pending-grant@tongji.edu.cn"
        browser = CsrfFlowClient()
        browser.verify_email(email)
        self.assertTrue(RegistrationVerification.objects.filter(verified_at__isnull=False).exists())
        registered = make_user(email=email)
        cancel_account(registered)
        invalid = browser.post_json(REGISTER_URL, dict(VALID, email=email))
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("verification", invalid.data["data"]["details"])
        self.assertFalse(User.objects.filter(email=email).exists())

    def test_in_flight_email_cannot_revive_a_cancelled_proof(self):
        browser = CsrfFlowClient()

        def finish_delivery(*args, **kwargs):
            cancel_account(self.user)
            return 1

        with patch("apps.accounts.verification.send_mail", side_effect=finish_delivery):
            result = browser.post_json("/api/v1/auth/register/send-code", {"email": self.user.email})
        self.assertEqual(result.status_code, 200)
        self.assertFalse(RegistrationVerification.objects.exists())
        self.assertFalse(User.objects.filter(email=self.user.email).exists())

    def test_publisher_stops_recruitment_and_chat_preserves_only_peer_text(self):
        job = make_recruitment(self.user, accepted_count=1)
        accepted = make_application(job, self.other, status="accepted")
        pending = make_application(job, make_user())
        low, high = sorted([self.user, self.other], key=lambda u: u.pk)
        chat = ChatConversation.objects.create(user_low=low, user_high=high)
        kept = ChatMessage.objects.create(conversation=chat, sender=self.other, content="对方消息")
        ChatMessage.objects.create(conversation=chat, sender=self.user, content="本人消息")
        ad = Announcement.objects.create(author=self.user, submitted_by=self.user, title="公告", content="正文",
                                         time_kind="event", event_at=clock.now())
        draft = AnnouncementSubmission.objects.create(submitter=self.other, title="投稿", content="原稿",
                    time_kind="event", event_at=clock.now(), claimed_by=self.user, claimed_until=clock.now())
        cancel_account(self.user)
        for obj in (job, accepted, pending, chat, ad, draft):
            obj.refresh_from_db()
        self.assertEqual((job.status, job.accepted_count, accepted.status, pending.status), ("closed", 1, "accepted", "rejected"))
        transition = pending.status_history.get()
        self.assertEqual((transition.reason, transition.actor_id), ("publisher_cancelled", None))
        self.assertTrue(Notification.objects.filter(recipient=accepted.applicant, application=accepted).exists())
        self.assertTrue(Notification.objects.filter(recipient=pending.applicant, application=pending).exists())
        self.assertIsNone(ad.submitted_by_id)
        self.assertNotEqual(job.publisher_id, self.user.pk)
        self.assertEqual(ad.author_id, job.publisher_id)
        self.assertIsNone(draft.claimed_by_id)
        self.assertEqual(chat.last_message_at, kept.created_at)
        self.client.force_login(self.other)
        conv = self.client.get("/api/v1/chat/conversations").data["data"]["items"][0]
        self.assertEqual(conv["peer"], {"uid": None, "nickname": "已注销用户", "role": None})
        self.assertEqual(conv["last_message"]["content"], "对方消息")
        self.assertIsNone(conv["last_message"]["recipient_uid"])
        self.assertFalse(ChatMessage.objects.filter(sender=self.user).exists())
        self.assertIsNone(self.client.get(f"/api/v1/recruitments/{job.pk}").data["data"]["publisher"]["uid"])
        self.assertIsNone(self.client.get(f"/api/v1/announcements/{ad.pk}").data["data"]["author"]["uid"])

    def test_withdrawal_and_anonymous_accepted_counts_survive_purge(self):
        full_at = clock.now()
        full = make_recruitment(self.other, status="full", accepted_count=2, max_headcount=2, full_at=full_at)
        accepted = make_application(full, self.user, status="accepted")
        make_application(full, make_user(), status="accepted")
        open_job = make_recruitment(self.other)
        pending = make_application(open_job, self.user)
        with TemporaryDirectory() as folder, override_settings(PRIVATE_FILE_ROOT=Path(folder)):
            files = [Path(folder) / app.resume_file.name for app in (pending, accepted)]
            for path in files:
                path.parent.mkdir(exist_ok=True, parents=True)
                path.write_bytes(b"%PDF-test")
            cancel_account(self.user)
            self.assertFalse(any(path.exists() for path in files))
        self.assertFalse(self.user.applications.exists())
        full.refresh_from_db()
        open_job.refresh_from_db()
        self.assertEqual((full.status, full.accepted_count, full.anonymous_counts), ("full", 2, {"accepted": 1}))
        self.assertEqual(open_job.anonymous_counts, {"withdrawn": 1})
        self.assertTrue(Notification.objects.filter(recipient=self.other, type="anonymous_withdrawal",
                                                    application__isnull=True, recruitment=open_job).exists())
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/api/v1/recruitments/{full.pk}").data["data"]["application_counts"]["accepted"], 2)
        due = full_at + timedelta(days=180)
        self.assertTrue(purge_expired_applications(full.pk, now=due))
        self.assertFalse(purge_expired_applications(full.pk, now=due))
        full.refresh_from_db()
        self.assertEqual((full.application_status_counts["accepted"], full.anonymous_counts), (2, {}))

    def test_governance_delete_moves_anonymous_acceptance_to_invalid_once(self):
        job = make_recruitment(self.other, accepted_count=1, max_headcount=1, status="full", full_at=clock.now())
        make_application(job, self.user, status="accepted")
        cancel_account(self.user)
        governance_delete_recruitment(make_user(is_admin=True), job.pk, reason="活动取消")
        job.refresh_from_db()
        self.assertEqual((job.accepted_count, job.anonymous_counts), (0, {"invalid": 1}))
        purge_expired_applications(job.pk, now=job.full_at + timedelta(days=180))
        job.refresh_from_db()
        self.assertEqual((job.application_status_counts["invalid"], job.application_status_counts["accepted"]), (1, 0))

    def test_failed_audit_rolls_back_files_and_identity(self):
        app = make_application(make_recruitment(self.other), self.user)
        with TemporaryDirectory() as folder, override_settings(PRIVATE_FILE_ROOT=Path(folder)):
            file = Path(folder) / app.resume_file.name
            file.parent.mkdir(parents=True)
            file.write_bytes(b"%PDF-test")
            with patch("apps.accounts.cancellation.record", side_effect=RuntimeError("审计写入失败")):
                with self.assertRaises(RuntimeError):
                    cancel_account(self.user)
            self.assertTrue(file.exists())
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.applications.filter(pk=app.pk).exists())
