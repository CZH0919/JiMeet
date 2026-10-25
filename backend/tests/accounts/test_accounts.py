import importlib
from datetime import timedelta
from unittest import mock

from django.contrib.auth import authenticate
from django.db import IntegrityError
from django.test import Client, SimpleTestCase, override_settings
from django.urls import clear_url_caches, resolve
from rest_framework.test import APIClient

from apps.accounts.identity import is_tongji_email, resolve_role
from apps.accounts.models import User
from apps.accounts.services import give_privacy_consent, login_with_sso, update_profile
from apps.accounts.sso import CasSSOProvider, DevSSOProvider, SSOIdentity
from apps.core import clock
from apps.core.errors import BizError, Forbidden, ValidationFailed
from tests.base import TxTestCase
from tests.factories import make_user


class IdentityTest(SimpleTestCase):
    def test_default_nickname_does_not_use_identity_fields(self):
        with mock.patch.object(User, "save"):
            user = User.objects.create_user("123", "陈同学", "123@tongji.edu.cn")
            self.assertRegex(user.nickname, r"^同学_[0-9a-f]{12}$")
            self.assertNotEqual(user.nickname, user.name)
            custom = User.objects.create_user("456", "林同学", "456@tongji.edu.cn", nickname="山间清风")
            self.assertEqual(custom.nickname, "山间清风")
            with mock.patch("apps.accounts.models.uuid.uuid4") as random_uuid:
                random_uuid.return_value.hex = "a" * 32
                same_name = User.objects.create_user("789", "同学_aaaaaaaaaaaa", "789@tongji.edu.cn")
                self.assertNotEqual(same_name.nickname, same_name.name)

    @override_settings(ALLOWED_EMAIL_DOMAINS=["tongji.edu.cn"])
    def test_identity_rules(self):
        for real_id, role in (("t123", "teacher"), ("T123", "teacher"), ("123", "student")):
            self.assertEqual(resolve_role(real_id), role)
        self.assertTrue(is_tongji_email("a@TONGJI.EDU.CN"))
        for email in ("invalid", "a@tongji.edu.cn.evil.com", "a@evil-tongji.edu.cn"):
            self.assertFalse(is_tongji_email(email))
        identity = DevSSOProvider().exchange({"real_id": "123"})
        self.assertEqual(identity, DevSSOProvider().exchange({"real_id": "123"}))
        for call in (lambda: CasSSOProvider().authorize_url("state"), lambda: CasSSOProvider().exchange({})):
            with self.assertRaisesMessage(NotImplementedError, "reserved"):
                call()


class AccountServicesTest(TxTestCase):
    def test_manager_default_nickname_and_explicit_nickname(self):
        user = make_user(name="陈同学")
        self.assertRegex(user.nickname, r"^同学_[0-9a-f]{12}$")
        self.assertNotEqual(user.nickname, user.name)
        custom = make_user(name="林同学", nickname="山间清风")
        self.assertEqual(custom.nickname, "山间清风")

    def test_create_repeat_and_bind(self):
        identity = SSOIdentity("T123", "教师", "t123@tongji.edu.cn", "subject-123")
        user = login_with_sso(identity)
        self.assertEqual((user.role, user.name, user.is_admin), ("teacher", "教师", False))
        self.assertRegex(user.nickname, r"^同学_[0-9a-f]{12}$")
        self.assertNotEqual(user.nickname, user.name)
        self.assertEqual(login_with_sso(identity).nickname, user.nickname)
        user.nickname = "自定义"
        user.save(update_fields=["nickname"])
        self.assertEqual(login_with_sso(identity).nickname, "自定义")
        self.assertEqual(User.objects.count(), 1)
        existing = make_user()
        bound = login_with_sso(SSOIdentity(existing.real_id, existing.name, existing.email, "new-subject"))
        self.assertEqual(bound.pk, existing.pk)
        self.assertEqual(bound.sso_subject, "new-subject")
        self.assertEqual(authenticate(identity=identity).pk, user.pk)

    def test_invalid_conflicting_and_disabled(self):
        user = make_user(sso_subject="bound")
        cases = (
            SSOIdentity("", "姓名", "a@tongji.edu.cn", "s"),
            SSOIdentity("123", "姓名", "a@example.com", "s"),
            SSOIdentity(user.real_id, user.name, user.email, "other"),
            SSOIdentity("different", user.name, user.email, "bound"),
            SSOIdentity("new", "姓名", user.email.upper(), "new"),
        )
        for identity in cases:
            with self.subTest(identity=identity), self.assertRaises(BizError) as caught:
                login_with_sso(identity)
            self.assertEqual(caught.exception.code, "AUTH_FAILED")
        user.is_active = False
        user.save(update_fields=["is_active"])
        with self.assertRaises(Forbidden):
            login_with_sso(SSOIdentity(user.real_id, user.name, user.email, "bound"))

    def test_disabled_unbound_account_is_not_bound(self):
        user = make_user(is_active=False)
        with self.assertRaises(Forbidden):
            login_with_sso(SSOIdentity(user.real_id, user.name, user.email, "unbound"))
        user.refresh_from_db()
        self.assertIsNone(user.sso_subject)

    def test_first_login_integrity_error_is_auth_failure(self):
        identity = SSOIdentity("new123", "新用户", "new123@tongji.edu.cn", "new-subject")
        with mock.patch.object(User.objects, "create_user", side_effect=IntegrityError("duplicate key")) as create:
            with self.assertRaises(BizError) as caught:
                login_with_sso(identity)
        create.assert_called_once()
        self.assertEqual((caught.exception.code, caught.exception.http_status), ("AUTH_FAILED", 401))
        self.assertNotIn("duplicate key", caught.exception.message)
        self.assertFalse(User.objects.filter(real_id=identity.real_id).exists())
        self.assertFalse(User.objects.filter(sso_subject=identity.subject).exists())

    def test_admin_password_login_falls_back_to_model_backend(self):
        user = User.objects.create_superuser(
            real_id="admin123", name="管理员", email="admin123@tongji.edu.cn", password="test-password",
        )
        authenticated = authenticate(username=user.real_id, password="test-password")
        self.assertEqual(authenticated.pk, user.pk)
        self.assertEqual(authenticated.backend, "django.contrib.auth.backends.ModelBackend")
        self.assertIsNone(authenticate(username=user.real_id, password="wrong-password"))
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get("/admin/login/").status_code, 200)
        response = client.post("/admin/login/", {
            "username": user.real_id, "password": "test-password", "next": "/admin/",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")
        self.assertEqual(client.session["_auth_user_backend"], "django.contrib.auth.backends.ModelBackend")
        self.assertEqual(client.get("/admin/").status_code, 200)

    def test_profile_and_consent(self):
        user = make_user(privacy=False)
        update_profile(user, nickname=" 昵称 ", email_notify_enabled=False)
        user.refresh_from_db()
        self.assertEqual((user.nickname, user.email_notify_enabled), ("昵称", False))
        for fields in ({"nickname": " "}, {"nickname": "字" * 33}, {"email_notify_enabled": "false"}):
            with self.assertRaises(ValidationFailed):
                update_profile(user, **fields)
        first = clock.now()
        with self.freeze_at(first):
            give_privacy_consent(user)
        with self.freeze_at(first + timedelta(days=1)):
            give_privacy_consent(user)
        self.assertEqual(user.privacy_consented_at, first)


@override_settings(DEBUG=True, ALLOW_DEV_LOGIN=True)
class AccountViewsTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self._reload_urls()
        self.addCleanup(self._reload_urls)
        self.client = APIClient(enforce_csrf_checks=True)

    def _reload_urls(self):
        import apps.accounts.urls
        importlib.reload(apps.accounts.urls)
        import config.urls
        importlib.reload(config.urls)
        clear_url_caches()

    def _login(self):
        response = self.client.get("/api/v1/auth/csrf")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", self.client.cookies)
        token = response.data["data"]["csrf_token"]
        response = self.client.post("/api/v1/auth/dev-login", {"real_id": "123"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        return self.client.cookies["csrftoken"].value

    def test_login_me_profile_consent_and_logout(self):
        token = self._login()
        response = self.client.get("/api/v1/me")
        self.assertEqual(set(response.data), {"code", "message", "data", "request_id"})
        self.assertEqual(set(response.data["data"]), {
            "uid", "nickname", "name", "role", "is_admin", "email", "email_notify_enabled", "privacy_consented",
        })
        self.assertFalse(response.data["data"]["privacy_consented"])
        response = self.client.patch("/api/v1/me", {"nickname": " 新昵称 ", "email_notify_enabled": False},
                                     format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["nickname"], "新昵称")
        for _ in range(2):
            response = self.client.post("/api/v1/me/privacy-consent", HTTP_X_CSRFTOKEN=token)
            self.assertTrue(response.data["data"]["privacy_consented"])
        self.assertEqual(self.client.post("/api/v1/auth/logout", HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)

    def test_csrf_and_field_rejections(self):
        self.assertEqual(self.client.post("/api/v1/auth/dev-login", {"real_id": "123"}, format="json").status_code, 403)
        token = self._login()
        self.assertEqual(self.client.patch("/api/v1/me", {"nickname": "x"}, format="json").status_code, 403)
        for fields in ({"is_admin": True}, {"role": "teacher"}, {"nickname": " "},
                       {"email_notify_enabled": "false"}, {"nickname": None}):
            with self.subTest(fields=fields):
                response = self.client.patch("/api/v1/me", fields, format="json", HTTP_X_CSRFTOKEN=token)
                self.assertEqual(response.status_code, 400)
        user = User.objects.get(real_id="123")
        self.assertFalse(user.is_admin)
        self.assertEqual(user.role, "student")

    def test_dev_route_requires_both_switches(self):
        for debug, allowed in ((False, True), (True, False), (False, False)):
            with self.subTest(debug=debug, allowed=allowed), override_settings(DEBUG=debug, ALLOW_DEV_LOGIN=allowed):
                self._reload_urls()
                from apps.accounts.urls import urlpatterns
                self.assertNotIn("auth-dev-login", [pattern.name for pattern in urlpatterns])
                self.assertEqual(self.client.post("/api/v1/auth/dev-login").status_code, 404)
        self._reload_urls()

    def test_runtime_switch_check_rejects_already_registered_route(self):
        from apps.accounts.views import DevLoginView
        route = resolve("/api/v1/auth/dev-login")
        self.assertIs(route.func.view_class, DevLoginView)
        token = self.client.get("/api/v1/auth/csrf").data["data"]["csrf_token"]
        for debug, allowed in ((False, True), (True, False), (False, False)):
            with self.subTest(debug=debug, allowed=allowed), override_settings(DEBUG=debug, ALLOW_DEV_LOGIN=allowed):
                # 不重载 URLconf，确保拒绝来自视图内部的配置检查。
                self.assertIs(resolve("/api/v1/auth/dev-login").func.view_class, DevLoginView)
                response = self.client.post("/api/v1/auth/dev-login", {"real_id": "runtime123"},
                                            format="json", HTTP_X_CSRFTOKEN=token)
                self.assertEqual((response.status_code, response.data["code"]), (404, "NOT_FOUND"))
        self.assertEqual(User.objects.count(), 0)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dev_login_optional_fields_match_me(self):
        token = self.client.get("/api/v1/auth/csrf").data["data"]["csrf_token"]
        response = self.client.post("/api/v1/auth/dev-login", {
            "real_id": "T456", "name": "开发教师", "email": "teacher456@tongji.edu.cn",
        }, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"code", "message", "data", "request_id"})
        self.assertEqual(response.data["code"], "OK")
        profile = self.client.get("/api/v1/me")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(response.data["data"], profile.data["data"])
        data = response.data["data"]
        self.assertEqual((data["name"], data["email"], data["role"]),
                         ("开发教师", "teacher456@tongji.edu.cn", "teacher"))
        self.assertRegex(data["nickname"], r"^同学_[0-9a-f]{12}$")
        self.assertNotEqual(data["nickname"], data["name"])
        user = User.objects.get(real_id="T456")
        self.assertEqual((user.name, user.email, user.uid), (data["name"], data["email"], data["uid"]))

    def test_anonymous_logout_requires_authentication(self):
        response = self.client.post("/api/v1/auth/logout")
        self.assertEqual((response.status_code, response.data["code"]), (401, "UNAUTHENTICATED"))
        self.assertEqual(set(response.data), {"code", "message", "data", "request_id"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_reserved_sso_and_anonymous_me(self):
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        for suffix in ("login", "callback"):
            response = self.client.get(f"/api/v1/auth/sso/{suffix}")
            self.assertEqual(response.status_code, 501)
            self.assertEqual((response.data["code"], response.data["message"]), ("INTERNAL_ERROR", "预留"))
