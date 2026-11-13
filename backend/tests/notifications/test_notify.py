from datetime import timedelta
from unittest import mock

from django.db import transaction
from django.test import SimpleTestCase

from apps.core import clock
from apps.notifications import mail, templates, types
from apps.notifications.models import EmailLog, Notification
from apps.notifications.service import notify
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class NotificationTypesTest(SimpleTestCase):
    def test_types_and_templates(self):
        self.assertEqual(types.APPLICATION_EVENTS, {value for value in types.ALL if value.startswith("application_")})
        self.assertEqual(types.REQUIRES_APPLICATION, types.APPLICATION_EVENTS | {types.RECRUITMENT_UPDATED})
        self.assertEqual(types.ANNOUNCEMENT_EVENTS, {types.ANNOUNCEMENT_ADMIN_REMOVED})
        for type in types.ALL:
            context = {"announcement_title": "测试公告"} if type in types.ANNOUNCEMENT_EVENTS else {"recruitment_title": "测试招聘"}
            title, content = templates.render(type, context)
            self.assertLessEqual(len(title), 100)
            self.assertIn("测试", content)
        _, announcement_content = templates.render(
            types.ANNOUNCEMENT_ADMIN_REMOVED,
            {"announcement_title": "测试公告", "reason_label": "违规内容"},
        )
        self.assertIn("测试公告", announcement_content)
        self.assertIn("原因：违规内容", announcement_content)
        for type, context in (("unknown", {}), (types.APPLICATION_UPDATED, {"applicant_name": "姓名"})):
            with self.assertRaises(ValueError):
                templates.render(type, context)

    def test_render_optional_context(self):
        context = {
            "recruitment_title": "测试招聘",
            "auto": True,
            "status_label": "已拒绝",
            "reason_label": "招聘已关闭",
            "link": "/applications/1",
        }
        _, content = templates.render(types.APPLICATION_REJECTED, context)
        for part in ("系统已自动处理", "已拒绝", "招聘已关闭", "/applications/1"):
            self.assertIn(part, content)
        _, plain = templates.render(types.APPLICATION_REJECTED, {"recruitment_title": "测试招聘"})
        self.assertNotIn("系统已自动处理", plain)
        # auto 只影响拒绝通知。
        _, accepted = templates.render(types.APPLICATION_ACCEPTED, {"recruitment_title": "t", "auto": True})
        self.assertNotIn("系统已自动处理", accepted)

    def test_mail_reservations(self):
        with self.assertLogs("apps.notifications.mail", level="INFO"):
            mail.dispatch(1)
        for function in (mail.send_email_log, mail.retry_pending_emails):
            with self.assertRaisesMessage(NotImplementedError, "reserved for week 2"):
                function(1)


class NotifyTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.publisher = make_user()
        self.applicant = make_user()
        self.r = make_recruitment(self.publisher)
        self.app = make_application(self.r, self.applicant)

    def _notify(self, **overrides):
        fields = dict(recipient=self.applicant, type=types.APPLICATION_ACCEPTED,
                      recruitment=self.r, application=self.app)
        fields.update(overrides)
        return notify(**fields)

    def test_requires_atomic_and_matching_objects(self):
        with self.assertRaises(RuntimeError):
            self._notify()
        other = make_recruitment(self.publisher)
        for overrides in ({"application": None}, {"recruitment": None}, {"recruitment": other},
                          {"type": types.RECRUITMENT_DELETED, "application": None}):
            with self.subTest(overrides=overrides), transaction.atomic(), self.assertRaises(ValueError):
                self._notify(**overrides)
        self.assertEqual(Notification.objects.count(), 0)

    def test_publisher_notifications_without_application(self):
        with mock.patch("apps.notifications.mail.dispatch"), transaction.atomic():
            for type in (types.RECRUITMENT_DELETED, types.RECRUITMENT_CLOSED, types.ADMIN_REMOVED):
                with self.subTest(type=type):
                    notification = self._notify(recipient=self.publisher, type=type, application=None)
                    self.assertIsNotNone(notification)
                    self.assertIsNone(notification.application_id)
                    self.assertEqual(notification.recruitment_id, self.r.pk)
        self.assertEqual(Notification.objects.filter(recipient=self.publisher).count(), 3)

    def test_recruitment_deleted_for_applicant_requires_application(self):
        with transaction.atomic(), self.assertRaises(ValueError):
            self._notify(type=types.RECRUITMENT_DELETED, application=None)
        with mock.patch("apps.notifications.mail.dispatch"), transaction.atomic():
            notification = self._notify(type=types.RECRUITMENT_DELETED)
        self.assertEqual(notification.application_id, self.app.pk)

    def test_invalid_context_does_not_create_records(self):
        with transaction.atomic(), self.assertRaises(ValueError):
            self._notify(context={"resume_content": "不允许的正文"})
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(EmailLog.objects.count(), 0)

    def test_no_email_log_or_dispatch_for_business_events(self):
        """Sprint2 起业务事件不再创建邮件待发记录或派发回调。"""
        with mock.patch("apps.notifications.mail.dispatch") as dispatch:
            with transaction.atomic():
                notification = self._notify()
            dispatch.assert_not_called()
        self.assertIsNotNone(notification)
        self.assertEqual(EmailLog.objects.count(), 0)

    def test_rollback_discards_notification(self):
        with mock.patch("apps.notifications.mail.dispatch") as dispatch:
            with self.assertRaises(ValueError), transaction.atomic():
                self._notify()
                raise ValueError("rollback")
            dispatch.assert_not_called()
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(EmailLog.objects.count(), 0)

    def test_email_preference_does_not_affect_in_app_notifications(self):
        self.applicant.email_notify_enabled = False
        with transaction.atomic():
            self.assertIsNotNone(self._notify())
        self.assertEqual(EmailLog.objects.count(), 0)

    def test_announcement_notification_links_only_announcement(self):
        from apps.announcements import services as announcement_services
        from apps.core.clock import now as clock_now

        admin = make_user(is_admin=True)
        with transaction.atomic():
            announcement = announcement_services.create_announcement(
                actor=admin, title="公告标题", content="正文", time_kind="event",
                event_at=clock_now() + timedelta(days=1),
            )
        with transaction.atomic():
            notification = notify(
                recipient=admin, type=types.ANNOUNCEMENT_ADMIN_REMOVED,
                announcement=announcement, context={"reason_label": "违规"},
            )
        self.assertEqual(
            (notification.announcement_id, notification.recruitment_id, notification.application_id),
            (announcement.pk, None, None),
        )
        for kwargs in (
            {"announcement": None},
            {"recruitment": self.r},
            {"application": self.app, "recruitment": self.r},
        ):
            with self.subTest(kwargs=kwargs), transaction.atomic(), self.assertRaises(ValueError):
                notify(
                    recipient=admin, type=types.ANNOUNCEMENT_ADMIN_REMOVED,
                    announcement=kwargs.pop("announcement", announcement), **kwargs
                )
        with transaction.atomic(), self.assertRaises(ValueError):
            notify(
                recipient=self.applicant, type=types.APPLICATION_ACCEPTED,
                recruitment=self.r, application=self.app, announcement=announcement,
            )

    def test_retention_applies_to_application_and_recruitment_events(self):
        now = clock.now()
        self.r.full_at = now - timedelta(days=180)
        with self.freeze_at(now), transaction.atomic():
            for type in (types.APPLICATION_REJECTED, types.RECRUITMENT_UPDATED, types.RECRUITMENT_DELETED):
                with self.subTest(type=type):
                    self.assertIsNone(self._notify(type=type))
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(EmailLog.objects.count(), 0)
        with transaction.atomic():
            notification = self._notify(recipient=self.publisher, type=types.ADMIN_REMOVED, application=None)
        self.assertIsNotNone(notification)
