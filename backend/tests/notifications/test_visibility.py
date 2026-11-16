"""通知长期读取、关联权限及显式已读的一致性回归。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest import mock

from django.db import close_old_connections, connections, transaction
from django.db.models import QuerySet

from apps.announcements.models import Announcement
from apps.core import clock
from apps.notifications import services, types
from apps.notifications.models import EmailLog, Notification
from apps.notifications.selectors import list_notifications
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.service import notify
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class NotificationVisibilityTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.owner, self.applicant = make_user(), make_user()
        self.admin = make_user(is_admin=True)
        self.r = make_recruitment(self.owner)
        self.app = make_application(self.r, self.applicant)

    def notice(self, **overrides):
        fields = dict(recipient=self.applicant, type=types.APPLICATION_ACCEPTED,
                      recruitment=self.r, application=self.app, title="申请已接受", content="历史通知")
        fields.update(overrides)
        return Notification.objects.create(**fields)

    def test_long_term_list_count_and_read_share_the_same_scope(self):
        notices = []
        for age in (179, 180, 181, 730):
            closed = clock.now() - timedelta(days=age)
            recruitment = make_recruitment(self.owner, status="closed", closed_at=closed,
                                          close_reason="manual", deadline=closed)
            application = make_application(recruitment, self.applicant, status="rejected", decided_at=closed)
            notice = self.notice(recruitment=recruitment, application=application)
            Notification.objects.filter(pk=notice.pk).update(created_at=closed)
            notices.append(notice)
        self.client.force_authenticate(self.applicant)
        listing = self.client.get("/api/v1/notifications").data["data"]
        self.assertEqual(listing["total"], 4)
        self.assertEqual([item["id"] for item in listing["items"]], [n.pk for n in notices])
        self.assertEqual(self.client.get("/api/v1/notifications/unread-count").data["data"]["unread_count"], 4)
        for _ in range(2):
            response = self.client.post(f"/api/v1/notifications/{notices[-1].pk}/read", {}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["data"]["is_read"])
        response = self.client.post("/api/v1/notifications/read-all", {}, format="json")
        self.assertEqual(response.data["data"]["updated_count"], 3)
        self.assertEqual(self.client.get("/api/v1/notifications?is_read=false").data["data"]["total"], 0)
        self.assertEqual(self.client.post("/api/v1/notifications/read-all", {}, format="json").data["data"]["updated_count"], 0)

    def test_invalid_links_and_other_users_are_excluded_from_all_operations(self):
        valid = self.notice()
        legacy = self.notice(recruitment=None, application=None)
        other_r = make_recruitment(self.admin)
        other_app = make_application(other_r, make_user())
        announcement = Announcement.objects.create(author=self.admin, title="公告", content="正文", time_kind="event", event_at=clock.now())
        hidden = [
            self.notice(recipient=self.admin),
            self.notice(recruitment=other_r, application=other_app),
            self.notice(recruitment=other_r, application=self.app),
            self.notice(application=None, recruitment=other_r),
            self.notice(type=types.ANNOUNCEMENT_ADMIN_REMOVED, recruitment=None, application=None, announcement=announcement),
        ]
        self.client.force_authenticate(self.applicant)
        self.assertEqual({row["id"] for row in self.client.get("/api/v1/notifications").data["data"]["items"]}, {valid.pk, legacy.pk})
        self.assertEqual(self.client.get("/api/v1/notifications/unread-count").data["data"]["unread_count"], 2)
        for item in hidden:
            self.assertEqual(self.client.post(f"/api/v1/notifications/{item.pk}/read", {}, format="json").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/notifications/read-all", {}, format="json").data["data"]["updated_count"], 2)
        self.assertFalse(Notification.objects.filter(pk__in=[n.pk for n in hidden], is_read=True).exists())

    def test_deleted_targets_are_flagged_without_restoring_public_access(self):
        accepted = self.notice()
        original_content = accepted.content
        self.r.deleted_at = clock.now()
        self.r.save(update_fields=["deleted_at"])
        announcement = Announcement.objects.create(author=self.applicant, title="旧公告", content="正文", time_kind="event", event_at=clock.now(), deleted_at=clock.now())
        removed = self.notice(recruitment=None, application=None, announcement=announcement,
                              type=types.ANNOUNCEMENT_ADMIN_REMOVED)
        self.client.force_authenticate(self.applicant)
        rows = self.client.get("/api/v1/notifications").data["data"]["items"]
        self.assertEqual({item["id"] for item in rows}, {accepted.pk, removed.pk})
        self.assertTrue(all(item["target_is_deleted"] for item in rows))
        self.assertEqual(next(item for item in rows if item["id"] == accepted.pk)["content"], original_content)
        self.assertEqual(self.client.get(f"/api/v1/recruitments/{self.r.pk}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/announcements/{announcement.pk}").status_code, 404)

    def test_target_preloading_preserves_stable_pagination(self):
        first, second, third = self.notice(), self.notice(), self.notice()
        Notification.objects.update(created_at=clock.now())
        with self.assertNumQueries(1):
            rows = NotificationSerializer(list_notifications(user=self.applicant), many=True).data
        self.assertEqual([item["id"] for item in rows], [third.pk, second.pk, first.pk])
        self.assertFalse(any(item["target_is_deleted"] for item in rows))
        self.client.force_authenticate(self.applicant)
        response = self.client.get("/api/v1/notifications?page=2&page_size=2")
        self.assertEqual([item["id"] for item in response.data["data"]["items"]], [first.pk])
        self.assertEqual(response.data["data"]["total"], 3)

    def test_reading_notifications_does_not_acknowledge_application_updates(self):
        self.app.has_unseen_update = True
        self.app.save(update_fields=["has_unseen_update"])
        version = self.app.updated_at
        notice = self.notice(recipient=self.owner, type=types.APPLICATION_UPDATED)
        self.client.force_authenticate(self.owner)
        self.client.get("/api/v1/notifications")
        self.client.post(f"/api/v1/notifications/{notice.pk}/read", {}, format="json")
        self.client.post("/api/v1/notifications/read-all", {}, format="json")
        self.app.refresh_from_db()
        self.assertTrue(self.app.has_unseen_update)
        self.assertEqual(self.app.updated_at, version)

    def test_read_all_does_not_consume_notifications_created_after_its_update(self):
        old = self.notice()
        updated, resume = Event(), Event()
        original = QuerySet.update

        def pause_after_update(queryset, **values):
            count = original(queryset, **values)
            if queryset.model is Notification and values == {"is_read": True}:
                updated.set()
                if not resume.wait(timeout=10):
                    raise TimeoutError("已读事务未获继续信号")
            return count

        def read_all():
            close_old_connections()
            try:
                return services.mark_all_notifications_read(user=self.applicant)
            finally:
                connections.close_all()

        with mock.patch.object(QuerySet, "update", pause_after_update), ThreadPoolExecutor(max_workers=1) as pool:
            task = pool.submit(read_all)
            try:
                self.assertTrue(updated.wait(timeout=10))
                new = self.notice()
            finally:
                resume.set()
            self.assertEqual(task.result(timeout=15), 1)
        old.refresh_from_db(); new.refresh_from_db()
        self.assertTrue(old.is_read)
        self.assertFalse(new.is_read)

    def test_event_recipient_and_target_validation_prevents_misdelivery(self):
        announcement = Announcement.objects.create(author=self.admin, title="公告", content="正文", time_kind="event", event_at=clock.now())
        cases = [
            dict(type=types.APPLICATION_SUBMITTED, recipient=self.applicant, recruitment=self.r, application=self.app),
            dict(type=types.APPLICATION_ACCEPTED, recipient=self.owner, recruitment=self.r, application=self.app),
            dict(type=types.RECRUITMENT_UPDATED, recipient=self.admin, recruitment=self.r, application=self.app),
            dict(type=types.RECRUITMENT_DELETED, recipient=self.owner, recruitment=self.r),
            dict(type=types.RECRUITMENT_CLOSED, recipient=self.applicant, recruitment=self.r),
            dict(type=types.ADMIN_REMOVED, recipient=self.owner, recruitment=self.r),
            dict(type=types.ANNOUNCEMENT_ADMIN_REMOVED, recipient=self.applicant, announcement=announcement, context={"reason_label": "违规"}),
        ]
        for fields in cases:
            with self.subTest(type=fields["type"]), transaction.atomic(), self.assertRaises(ValueError):
                notify(**fields)
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(EmailLog.objects.exists())

    def test_author_title_is_taken_from_target_and_email_preferences_do_not_send_mail(self):
        for enabled in (False, True):
            self.applicant.email_notify_enabled = enabled
            self.applicant.save(update_fields=["email_notify_enabled"])
            with mock.patch("apps.notifications.mail.dispatch") as dispatch, transaction.atomic():
                notice = notify(recipient=self.applicant, type=types.APPLICATION_ACCEPTED,
                                recruitment=self.r, application=self.app, context={"recruitment_title": "伪造名称"})
            self.assertIn(self.r.title, notice.content)
            self.assertNotIn("伪造名称", notice.content)
            dispatch.assert_not_called()
        self.assertEqual(Notification.objects.count(), 2)
        self.assertFalse(EmailLog.objects.exists())
