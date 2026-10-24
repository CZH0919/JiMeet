import importlib
import os
import sys
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.chat.models import ChatConversation
from apps.core.clock import now
from apps.notifications.models import EmailLog, Notification
from apps.recruitments.models import RecruitmentTag
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_tag, make_user


class TxTestCaseTest(TxTestCase):
    def test_login_sets_session_user(self):
        user = make_user()
        self.login(user)
        response = self.client.get("/api/v1/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_freeze_at(self):
        moment = datetime(2026, 3, 1, tzinfo=dt_timezone.utc)
        with self.freeze_at(moment):
            self.assertEqual(now(), moment)
        self.assertNotEqual(now(), moment)

    def test_reset_sequences_disabled(self):
        self.assertFalse(self.reset_sequences)


class MakeUserTest(TxTestCase):
    def test_defaults(self):
        user = make_user()
        self.assertEqual(user.role, "student")
        self.assertFalse(user.is_admin)
        self.assertIsNotNone(user.privacy_consented_at)
        self.assertTrue(user.check_password("") is False)
        self.assertFalse(user.has_usable_password())

    def test_teacher_and_admin(self):
        user = make_user(role="teacher", is_admin=True)
        self.assertEqual(user.role, "teacher")
        self.assertTrue(user.is_admin)
        self.assertTrue(user.real_id.startswith("t"))

    def test_privacy_false(self):
        self.assertIsNone(make_user(privacy=False).privacy_consented_at)

    def test_unique_real_id(self):
        first = make_user()
        second = make_user()
        self.assertNotEqual(first.real_id, second.real_id)


class UserManagerTest(TxTestCase):
    def test_create_user_defaults(self):
        user = User.objects.create_user("s1", "张三", "S1@tongji.edu.cn")
        self.assertEqual(user.role, "student")
        self.assertEqual(user.name, "张三")
        self.assertRegex(user.nickname, r"^同学_[0-9a-f]{12}$")
        self.assertNotEqual(user.nickname, user.name)
        self.assertEqual(user.email, "S1@tongji.edu.cn")
        self.assertFalse(user.is_admin)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_usable_password())

    def test_create_user_with_password(self):
        user = User.objects.create_user("s2", "李四", "s2@tongji.edu.cn", "pw-12345")
        self.assertTrue(user.check_password("pw-12345"))

    def test_create_superuser_defaults(self):
        user = User.objects.create_superuser("t1", "王老师", "t1@tongji.edu.cn", "pw-12345")
        self.assertEqual(user.role, "teacher")
        self.assertTrue(user.is_admin)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("pw-12345"))

    def test_empty_real_id_or_name_rejected(self):
        with self.assertRaises(ValueError):
            User.objects.create_user("", "张三", "a@tongji.edu.cn")
        with self.assertRaises(ValueError):
            User.objects.create_user("s3", "", "a@tongji.edu.cn")
        self.assertEqual(User.objects.count(), 0)


class ModelStrTest(TxTestCase):
    def test_str_only_contains_class_and_pk(self):
        publisher = make_user(role="teacher", name="敏感姓名")
        applicant = make_user()
        recruitment = make_recruitment(publisher, title="敏感标题")
        application = make_application(recruitment, applicant)
        notification = Notification.objects.create(
            recipient=applicant, type="t", title="敏感通知", content="敏感内容",
        )
        low, high = sorted([publisher, applicant], key=lambda user: user.pk)
        conversation = ChatConversation.objects.create(user_low=low, user_high=high)
        objects = [
            publisher,
            recruitment,
            make_tag(name="敏感标签"),
            RecruitmentTag.objects.create(recruitment=recruitment, tag=make_tag()),
            application,
            notification,
            EmailLog.objects.create(notification=notification, to_email="secret@x.com"),
            AuditLog.objects.create(action="a", target_type="request", reason="敏感原因"),
            conversation,
            conversation.messages.create(sender=low, content="敏感正文"),
        ]
        for obj in objects:
            with self.subTest(model=type(obj).__name__):
                self.assertEqual(str(obj), f"{type(obj).__name__}({obj.pk})")


class SettingsTest(SimpleTestCase):
    def test_base_settings(self):
        self.assertIs(settings.ATOMIC_REQUESTS, False)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")
        self.assertEqual(settings.TIME_ZONE, "Asia/Shanghai")
        self.assertTrue(settings.USE_TZ)
        self.assertEqual(settings.MAX_HEADCOUNT_LIMIT, 50)
        self.assertEqual(
            settings.MIDDLEWARE[0],
            "apps.core.middleware.RequestIdMiddleware",
        )

    def test_private_root_outside_media_and_static(self):
        private = Path(settings.PRIVATE_FILE_ROOT).resolve()
        for public in (settings.MEDIA_ROOT, settings.STATIC_ROOT):
            public = Path(public).resolve()
            self.assertNotEqual(private, public)
            self.assertNotIn(public, private.parents)
            self.assertNotIn(private, public.parents)

    def _import_prod(self, **env):
        base = {
            "DJANGO_SECRET_KEY": "k",
            "DJANGO_ALLOWED_HOSTS": "example.com",
            "DB_NAME": "n",
            "DB_USER": "u",
            "DB_PASSWORD": "p",
            "DB_HOST": "h",
        }
        base.update(env)
        saved = sys.modules.pop("config.settings.prod", None)
        try:
            with mock.patch.dict(os.environ, base, clear=True):
                return importlib.import_module("config.settings.prod")
        finally:
            sys.modules.pop("config.settings.prod", None)
            if saved is not None:
                sys.modules["config.settings.prod"] = saved

    def test_prod_settings(self):
        prod = self._import_prod()
        self.assertFalse(prod.DEBUG)
        self.assertIs(prod.ALLOW_DEV_LOGIN, False)
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)

    def test_prod_requires_env(self):
        for name in ("DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST"):
            with self.subTest(missing=name):
                with self.assertRaises(RuntimeError):
                    self._import_prod(**{name: ""})

    def test_prod_rejects_dev_login(self):
        with self.assertRaises(RuntimeError):
            self._import_prod(ALLOW_DEV_LOGIN="true")
