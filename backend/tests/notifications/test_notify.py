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
        for type in types.ALL:
            title, content = templates.render(type, {"recruitment_title": "测试招聘"})
            self.assertLessEqual(len(title), 100)
            self.assertIn("测试招聘", content)
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

    def test_email_created_and_dispatched_only_after_commit(self):
        with mock.patch("apps.notifications.mail.dispatch") as dispatch:
            with transaction.atomic():
                notification = self._notify()
                log = EmailLog.objects.get(notification=notification)
                self.assertEqual((log.status, log.attempts, log.to_email), ("pending", 0, self.applicant.email))
                dispatch.assert_not_called()
            dispatch.assert_called_once_with(log.pk)
        log.refresh_from_db()
        self.assertEqual(log.status, "pending")

    def test_rollback_discards_notification_email_and_callback(self):
        with mock.patch("apps.notifications.mail.dispatch") as dispatch:
            with self.assertRaises(ValueError), transaction.atomic():
                self._notify()
                raise ValueError("rollback")
            dispatch.assert_not_called()
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(EmailLog.objects.count(), 0)

    def test_email_disabled(self):
        self.applicant.email_notify_enabled = False
        with mock.patch("apps.notifications.mail.dispatch") as dispatch, transaction.atomic():
            self.assertIsNotNone(self._notify())
        dispatch.assert_not_called()
        self.assertEqual(EmailLog.objects.count(), 0)

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
