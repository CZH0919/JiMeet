from apps.core.choices import ApplicationStatus
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.notifications.types import APPLICATION_UPDATED
from rest_framework.test import APIClient
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class ApplicationMutationAPITest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.publisher = make_user()
        self.applicant = make_user()
        self.r = make_recruitment(self.publisher)
        self.app = make_application(self.r, self.applicant)

    def test_patch_updates_note_and_sets_publisher_unread_marker(self):
        self.client.force_authenticate(user=self.applicant)
        response = self.client.patch(
            f"/api/v1/applications/{self.app.pk}",
            {"note": "更新后的说明"}, format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["note"], "更新后的说明")
        self.app.refresh_from_db()
        self.assertTrue(self.app.has_unseen_update)
        notification = Notification.objects.get(type=APPLICATION_UPDATED)
        self.assertEqual(notification.recipient_id, self.publisher.pk)
        audit = AuditLog.objects.get(action=actions.APPLICATION_UPDATE)
        self.assertEqual((audit.target_type, audit.target_id, audit.actor_id), (
            "application", self.app.pk, self.applicant.pk,
        ))

    def test_patch_rejects_empty_or_unknown_fields(self):
        self.client.force_authenticate(user=self.applicant)
        for data in ({}, {"status": "accepted"}):
            with self.subTest(data=data):
                response = self.client.patch(
                    f"/api/v1/applications/{self.app.pk}", data, format="multipart",
                )
                self.assertEqual(response.status_code, 400)

    def test_publisher_read_requires_version_and_preserves_content_version(self):
        self.client.force_authenticate(user=self.applicant)
        self.client.patch(
            f"/api/v1/applications/{self.app.pk}",
            {"note": "更新"}, format="multipart",
        )
        self.client.force_authenticate(user=self.publisher)
        detail = self.client.get(f"/api/v1/applications/{self.app.pk}")
        version = detail.data["data"]["updated_at"]
        missing_version = self.client.post(
            f"/api/v1/applications/{self.app.pk}/read", {}, format="json",
        )
        self.assertEqual(missing_version.status_code, 400)

        acknowledged = self.client.post(
            f"/api/v1/applications/{self.app.pk}/read",
            {"seen_updated_at": version}, format="json",
        )
        self.assertEqual(acknowledged.status_code, 200)
        self.assertFalse(acknowledged.data["data"]["has_unseen_update"])
        self.assertEqual(acknowledged.data["data"]["updated_at"], version)

    def test_accept_action_is_registered_and_returns_application_detail(self):
        self.client.force_authenticate(user=self.publisher)
        response = self.client.post(
            f"/api/v1/applications/{self.app.pk}/accept", {}, format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], ApplicationStatus.ACCEPTED)
        self.assertIsNotNone(response.data["data"]["decided_at"])

    def test_application_actions_keep_session_csrf_protection(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.publisher)
        csrf = client.get("/api/v1/auth/csrf")
        token = csrf.data["data"]["csrf_token"]

        rejected = client.post(
            f"/api/v1/applications/{self.app.pk}/reject", {}, format="json",
        )
        self.assertEqual(rejected.status_code, 403)

        accepted = client.post(
            f"/api/v1/applications/{self.app.pk}/reject", {},
            format="json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(accepted.status_code, 200)
