from datetime import timedelta

from apps.core import clock
from apps.core.choices import RecruitmentStatus
from apps.notifications.models import Notification
from apps.notifications.types import APPLICATION_ACCEPTED
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class NotificationAPITest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.now = clock.now()
        self.publisher = make_user()
        self.applicant = make_user()
        self.stranger = make_user()
        self.r = make_recruitment(self.publisher)
        self.app = make_application(self.r, self.applicant)
        self.notification = self.make_notification(self.applicant, application=self.app, recruitment=self.r)

    def make_notification(self, recipient, *, application=None, recruitment=None, is_read=False):
        return Notification.objects.create(
            recipient=recipient, type=APPLICATION_ACCEPTED, title="申请已接受", content="状态已更新",
            application=application, recruitment=recruitment, is_read=is_read,
        )

    def login_as(self, user):
        self.client.force_authenticate(user=user)

    def test_list_filters_read_state_and_unread_count(self):
        self.make_notification(self.applicant, application=self.app, recruitment=self.r, is_read=True)
        self.login_as(self.applicant)

        response = self.client.get("/api/v1/notifications?is_read=false")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["total"], 1)
        self.assertEqual(response.data["data"]["items"][0]["id"], self.notification.pk)

        count = self.client.get("/api/v1/notifications/unread-count")
        self.assertEqual(count.data["data"], {"unread_count": 1})

    def test_invalid_is_read_query_is_rejected(self):
        self.login_as(self.applicant)
        for value in ("1", "yes", ""):
            with self.subTest(value=value):
                response = self.client.get(f"/api/v1/notifications?is_read={value}")
                self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/v1/notifications?is_read=true&is_read=false")
        self.assertEqual(response.status_code, 400)

    def test_mark_single_read_is_idempotent_and_private(self):
        self.login_as(self.applicant)
        path = f"/api/v1/notifications/{self.notification.pk}/read"
        first = self.client.post(path, {}, format="json")
        second = self.client.post(path, {}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["data"]["id"], self.notification.pk)
        self.assertTrue(first.data["data"]["is_read"])
        self.assertEqual(second.status_code, 200)

        self.client.force_authenticate(user=self.stranger)
        denied = self.client.post(path, {}, format="json")
        self.assertEqual(denied.status_code, 404)

    def test_read_all_only_marks_visible_unread_notifications(self):
        self.make_notification(self.applicant, application=self.app, recruitment=self.r)
        self.make_notification(self.applicant, is_read=True)
        self.login_as(self.applicant)

        response = self.client.post("/api/v1/notifications/read-all", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], {"updated_count": 2})
        self.assertEqual(
            Notification.objects.filter(recipient=self.applicant, is_read=False).count(), 0,
        )

    def test_expired_linked_notifications_are_hidden_from_all_reads(self):
        self.r.full_at = self.now - timedelta(days=180)
        self.r.status = RecruitmentStatus.FULL
        self.r.save(update_fields=["full_at", "status"])
        independent = self.make_notification(self.applicant)
        self.login_as(self.applicant)

        listing = self.client.get("/api/v1/notifications")
        count = self.client.get("/api/v1/notifications/unread-count")
        single = self.client.post(
            f"/api/v1/notifications/{self.notification.pk}/read", {}, format="json",
        )
        self.assertEqual([item["id"] for item in listing.data["data"]["items"]], [independent.pk])
        self.assertIsNone(listing.data["data"]["items"][0]["application_id"])
        self.assertIsNone(listing.data["data"]["items"][0]["recruitment_id"])
        self.assertEqual(count.data["data"], {"unread_count": 1})
        self.assertEqual(single.status_code, 404)

    def test_unknown_fields_and_empty_body_contract(self):
        self.login_as(self.applicant)
        response = self.client.post(
            f"/api/v1/notifications/{self.notification.pk}/read",
            {"is_read": False}, format="json",
        )
        self.assertEqual(response.status_code, 400)
