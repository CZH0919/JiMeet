"""邮箱密码注册登录与管理员配置的接口及服务测试，用例对应 AT-01/AT-02。"""
import io
import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from rest_framework.test import APIClient

from apps.accounts import ratelimit, verification
from apps.accounts.models import AuthFailure, User
from apps.accounts.services import register_with_password
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.core import clock
from apps.core.errors import ErrorCode, ValidationFailed
from tests.base import TxTestCase
from tests.factories import make_user

REGISTER_URL = "/api/v1/auth/register"
SEND_CODE_URL = REGISTER_URL + "/send-code"
VERIFY_CODE_URL = REGISTER_URL + "/verify-code"
LOGIN_URL = "/api/v1/auth/login"
LOGIN_SEND_CODE_URL = LOGIN_URL + "/send-code"
LOGOUT_URL = "/api/v1/auth/logout"
CSRF_URL = "/api/v1/auth/csrf"
ME_URL = "/api/v1/me"

VALID = {
    "email": "newuser@tongji.edu.cn",
    "password": "Sprint2-Auth#2026",
    "password_confirm": "Sprint2-Auth#2026",
    "name": "新同学",
    "role": "student",
}


def register_payload(**overrides):
    """构造注册载荷；覆盖 password 时同步确认密码，除非显式覆盖。"""
    payload = dict(VALID, **overrides)
    if "password" in overrides and "password_confirm" not in overrides:
        payload["password_confirm"] = overrides["password"]
    return payload


class CsrfFlowClient(APIClient):
    """开启 CSRF 校验的客户端，按契约顺序自动携带令牌。"""

    def __init__(self):
        super().__init__(enforce_csrf_checks=True)
        self.csrf_token = self._fetch_token()

    def _fetch_token(self) -> str:
        response = self.get(CSRF_URL)
        return response.data["data"]["csrf_token"]

    def delivered_code(self, email: str, purpose: str = "registration") -> str:
        """通过真实发码视图，从本次测试投递的邮件中读取验证码。"""
        count = len(mail.outbox)
        url = SEND_CODE_URL if purpose == "registration" else LOGIN_SEND_CODE_URL
        response = self.post_json(url, {"email": email})
        if response.status_code != 200 or len(mail.outbox) != count + 1:
            raise AssertionError("测试邮件未生成")
        message = mail.outbox[-1]
        if message.to != [email.strip().lower()]:
            raise AssertionError("测试邮件收件地址不匹配")
        return re.search(r"验证码为 ([0-9]{6})", message.body).group(1)

    def verify_email(self, email: str):
        """完成发码和验码，返回用于注册的匿名会话键。"""
        code = self.delivered_code(email)
        response = self.post_json(VERIFY_CODE_URL, {"email": email, "code": code})
        if response.status_code != 200:
            raise AssertionError("邮箱验证未通过")
        return self.session.session_key

    def post_json(self, url: str, payload: dict):
        """携带当前 CSRF 令牌提交 JSON；令牌轮换后自动刷新。"""
        response = self.post(
            url, data=payload, format="json", HTTP_X_CSRFTOKEN=self.csrf_token
        )
        self.csrf_token = self._fetch_token()
        return response


class RegisterLoginAPITest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.client = CsrfFlowClient()

    def test_full_flow_register_logout_login_profile(self):
        """AT-01-01/10：CSRF → 发码与验码 → 注册 → 退出 → 登录 → 读取本人资料。"""
        self.client.verify_email(VALID["email"])
        response = self.client.post_json(REGISTER_URL, register_payload())
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertEqual((data["email"], data["name"], data["role"]), (
            VALID["email"], VALID["name"], "student",
        ))
        self.assertFalse(data["is_admin"])
        self.assertFalse(data["privacy_consented"])
        self.assertNotIn("password", data)
        self.assertNotIn("real_id", data)
        self.assertEqual(response["Cache-Control"], "private, no-store")

        me = self.client.get(ME_URL)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["data"]["email"], VALID["email"])

        logout = self.client.post_json(LOGOUT_URL, {})
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get(ME_URL).status_code, 401)

        login = self.client.post_json(LOGIN_URL, {
            "email": VALID["email"], "password": VALID["password"],
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data["data"]["email"], VALID["email"])
        self.assertEqual(login["Cache-Control"], "private, no-store")
        self.assertEqual(self.client.get(ME_URL).status_code, 200)

    def test_register_requires_csrf_for_anonymous(self):
        """AT-01-07：匿名缺少 CSRF 令牌被拒。"""
        plain = APIClient(enforce_csrf_checks=True)
        response = plain.post(REGISTER_URL, register_payload(), format="json")
        self.assertEqual(response.status_code, 403)
        response = plain.post(LOGIN_URL, {
            "email": VALID["email"], "password": VALID["password"],
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(User.objects.count(), 0)

    def test_register_domain_strictness(self):
        """AT-01-02：相似域名、附加后缀均拒绝。"""
        for email in (
            "a@tongji.edu.cn.evil.com", "a@evil-tongji.edu.cn", "a@tongji.edu.cn.com",
            "a@tongji.edu.cnx", "a@xontji.edu.cn",
        ):
            payload = register_payload(email=email)
            response = self.client.post_json(REGISTER_URL, payload)
            self.assertEqual(response.status_code, 400, email)
        self.assertEqual(User.objects.count(), 0)

    def test_register_case_insensitive_duplicate_keeps_account(self):
        """AT-01-03：大小写变体重复注册被拒，已有账号不被覆盖。"""
        self.client.verify_email("A@Tongji.Edu.CN")
        first = self.client.post_json(REGISTER_URL, register_payload(email="A@Tongji.Edu.CN"))
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data["data"]["email"], "a@tongji.edu.cn")
        original = User.objects.get(email="a@tongji.edu.cn")
        password_hash = original.password

        second = self.client.post_json(REGISTER_URL, register_payload(email="a@tongji.edu.cn", password="Another#Pass9"))
        self.assertEqual(second.status_code, 400)
        self.assertEqual(User.objects.count(), 1)
        original.refresh_from_db()
        self.assertEqual(original.password, password_hash)

    def test_registration_collision_after_verification_consumes_grant(self):
        """验码后邮箱已被另一会话注册时，保留先建账号并消费本次资格。"""
        self.client.verify_email(VALID["email"])
        original = make_user(email=VALID["email"], password="Initial!Password573")
        original_hash = original.password
        response = self.client.post_json(REGISTER_URL, register_payload())
        self.assertEqual((response.status_code, response.data["code"]), (400, ErrorCode.VALIDATION_ERROR))
        self.assertEqual(response.data["data"]["details"]["email"], "该邮箱已注册，请登录")
        original.refresh_from_db()
        self.assertEqual((User.objects.count(), original.password), (1, original_hash))
        retry = self.client.post_json(REGISTER_URL, register_payload())
        self.assertIn("verification", retry.data["data"]["details"])

    def test_unrelated_integrity_error_rolls_back_grant(self):
        session_key = self.client.verify_email(VALID["email"])
        with mock.patch("apps.accounts.models.UserManager.create_user", side_effect=IntegrityError("constraint error")):
            with self.assertRaises(IntegrityError):
                register_with_password(**VALID, session_key=session_key)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(self.client.post_json(REGISTER_URL, register_payload()).status_code, 201)

    def test_register_password_policy(self):
        """AT-01-05：弱密码、纯数字、过短密码被拒。"""
        for password in ("1234567890", "password", "Abc123!"):
            response = self.client.post_json(REGISTER_URL, register_payload(password=password))
            self.assertEqual(response.status_code, 400, password)
            self.assertEqual(response.data["code"], ErrorCode.VALIDATION_ERROR)
        self.assertEqual(User.objects.count(), 0)

    def test_register_rejects_permission_fields_and_unknown(self):
        """AT-01-06：权限字段与未知字段被拒，不建账号。"""
        for extra in ({"is_admin": True}, {"is_staff": True}, {"unknown": 1}):
            response = self.client.post_json(REGISTER_URL, register_payload(**extra))
            self.assertEqual(response.status_code, 400, extra)
        self.assertEqual(User.objects.count(), 0)

    def test_register_response_has_no_internal_identifiers(self):
        """AT-01-13/14：注册与登录响应不泄露内部标识，不声明实名核验。"""
        self.client.verify_email(VALID["email"])
        response = self.client.post_json(REGISTER_URL, register_payload())
        data = response.data["data"]
        self.assertEqual(
            set(data), {"uid", "nickname", "name", "role", "is_admin", "email",
                        "email_notify_enabled", "privacy_consented"},
        )
        self.assertNotIn("sso_subject", data)
        self.assertNotIn("real_id", data)


class RegisterFieldRequirementTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.client = CsrfFlowClient()

    def test_role_and_confirm_password_are_required(self):
        """AT-01-16：身份必填、确认密码必填且一致；注册后本人资料身份不可改。"""
        self.client.verify_email(VALID["email"])
        missing_role = register_payload()
        missing_role.pop("role")
        missing_confirm = register_payload()
        missing_confirm.pop("password_confirm")
        for payload in (missing_role, missing_confirm, register_payload(password_confirm="Different#Pass9")):
            with self.subTest(fields=sorted(payload)):
                response = self.client.post_json(REGISTER_URL, payload)
                self.assertEqual(response.status_code, 400)
        response = self.client.post_json(REGISTER_URL, register_payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get(ME_URL).data["data"]["role"], "student")

    def test_mismatch_detail_names_confirm_field(self):
        self.client.verify_email(VALID["email"])
        response = self.client.post_json(
            REGISTER_URL, register_payload(password_confirm="Different#Pass9"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password_confirm", response.data["data"]["details"])


class LoginCodeTest(TxTestCase):
    """AT-01-17：验证码登录，绑定用途/邮箱/会话，成功后一次性消费。"""

    def setUp(self):
        super().setUp()
        self.client = CsrfFlowClient()
        self.user = make_user(email="coder@tongji.edu.cn", password="Coder#Pass2026")

    def test_code_login_success_and_one_time_consume(self):
        code = self.client.delivered_code(self.user.email, purpose="login")
        response = self.client.post_json(LOGIN_URL, {"email": self.user.email, "code": code})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(ME_URL).status_code, 200)
        reuse = self.client.post_json(LOGIN_URL, {"email": self.user.email, "code": code})
        self.assertEqual(reuse.status_code, 400)

    def test_code_login_wrong_session_bound_and_expired(self):
        start = clock.now()
        code = self.client.delivered_code(self.user.email, purpose="login")
        wrong = self.client.post_json(LOGIN_URL, {"email": self.user.email, "code": "000000"})
        self.assertEqual(wrong.status_code, 400)
        stolen = CsrfFlowClient().post_json(LOGIN_URL, {"email": self.user.email, "code": code})
        self.assertEqual(stolen.status_code, 400)

        with self.freeze_at(start + timedelta(seconds=61)):
            fresh = self.client.delivered_code(self.user.email, purpose="login")
        with self.freeze_at(start + timedelta(minutes=7)):
            response = self.client.post_json(LOGIN_URL, {"email": self.user.email, "code": fresh})
        self.assertEqual(response.status_code, 400)

    def test_code_login_five_strikes_invalidate(self):
        code = self.client.delivered_code(self.user.email, purpose="login")
        for _ in range(5):
            response = self.client.post_json(LOGIN_URL, {"email": self.user.email, "code": "000000"})
            self.assertEqual(response.status_code, 400)
        # 连续错码作废后，正确的验证码也不再可用（服务层直接验证作废语义）。
        with self.assertRaises(ValidationFailed):
            verification.consume_login_code(
                email=self.user.email, code=code,
                session_key=verification.registration_session_key(self.client.session),
            )
        # 同时登录失败限流已生效。
        limited = self.client.post_json(LOGIN_URL, {"email": self.user.email, "code": code})
        self.assertEqual(limited.status_code, 429)

    def test_code_login_requires_registered_active_account(self):
        ghost = self.client.delivered_code("ghost@tongji.edu.cn", purpose="login")
        response = self.client.post_json(LOGIN_URL, {"email": "ghost@tongji.edu.cn", "code": ghost})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], ErrorCode.AUTH_FAILED)

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        code = self.client.delivered_code(self.user.email, purpose="login")
        response = self.client.post_json(LOGIN_URL, {"email": self.user.email, "code": code})
        self.assertEqual(response.status_code, 403)

    def test_registration_code_cannot_login(self):
        """串用：注册验证码不能用于验证码登录（用途隔离）。"""
        code = self.client.delivered_code(self.user.email, purpose="registration")
        response = self.client.post_json(LOGIN_URL, {"email": self.user.email, "code": code})
        self.assertEqual(response.status_code, 400)

    def test_login_password_xor_code(self):
        for payload in (
            {"email": self.user.email},
            {"email": self.user.email, "password": "Coder#Pass2026", "code": "123456"},
        ):
            response = self.client.post_json(LOGIN_URL, payload)
            self.assertEqual(response.status_code, 400)

    def test_login_send_code_uniform_and_shared_cool_down(self):
        first = self.client.post_json(LOGIN_SEND_CODE_URL, {"email": self.user.email})
        ghost = self.client.post_json(LOGIN_SEND_CODE_URL, {"email": "ghost@tongji.edu.cn"})
        self.assertEqual((first.status_code, ghost.status_code), (200, 200))
        self.assertEqual(first.data["data"], {"expires_in": 300, "resend_after": 60})
        self.assertEqual(first.data["data"], ghost.data["data"])
        # 与注册验证码共享同邮箱 60 秒重发间隔
        shared = self.client.post_json(SEND_CODE_URL, {"email": self.user.email})
        self.assertEqual(shared.status_code, 429)


class LoginSecurityTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.client = CsrfFlowClient()
        self.user = make_user(email="member@tongji.edu.cn", password="Member#Pass2026")

    def test_login_failures_uniform_and_disabled_account(self):
        """AT-01-08/09：错误凭据统一 401，停用账号 403。"""
        messages = []
        for payload in (
            {"email": "missing@tongji.edu.cn", "password": "Whatever#2026"},
            {"email": self.user.email, "password": "Wrong#Pass2026"},
        ):
            response = self.client.post_json(LOGIN_URL, payload)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.data["code"], ErrorCode.AUTH_FAILED)
            messages.append(response.data["message"])
        self.assertEqual(messages[0], messages[1])

        unusable = make_user(email="nopass@tongji.edu.cn")
        response = self.client.post_json(LOGIN_URL, {
            "email": unusable.email, "password": "Whatever#2026",
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["message"], messages[0])

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post_json(LOGIN_URL, {
            "email": self.user.email, "password": "Member#Pass2026",
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], ErrorCode.FORBIDDEN)

    def test_login_rate_limit_email_key(self):
        """AT-01-11/12：同邮箱 5 次失败后 429；成功登录清零；窗口滑过恢复。"""
        for _ in range(5):
            response = self.client.post_json(LOGIN_URL, {
                "email": self.user.email, "password": "Wrong#Pass2026",
            })
            self.assertEqual(response.status_code, 401)
        limited = self.client.post_json(LOGIN_URL, {
            "email": self.user.email, "password": "Wrong#Pass2026",
        })
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.data["code"], ErrorCode.RATE_LIMITED)

        with self.freeze_at(clock_moment_after_window()):
            response = self.client.post_json(LOGIN_URL, {
                "email": self.user.email, "password": "Member#Pass2026",
            })
            self.assertEqual(response.status_code, 200)

        for _ in range(3):
            self.client.post_json(LOGIN_URL, {
                "email": self.user.email, "password": "Wrong#Pass2026",
            })
        self.assertEqual(self.client.post_json(LOGIN_URL, {
            "email": self.user.email, "password": "Member#Pass2026",
        }).status_code, 200)
        for _ in range(5):
            response = self.client.post_json(LOGIN_URL, {
                "email": self.user.email, "password": "Wrong#Pass2026",
            })
            self.assertEqual(response.status_code, 401)

    def test_login_rate_limit_ip_key_independent(self):
        """AT-01-11：同 IP 换邮箱仍受限；邮箱键与 IP 键独立。"""
        for index in range(20):
            response = self.client.post_json(LOGIN_URL, {
                "email": f"probe{index}@tongji.edu.cn", "password": "Wrong#Pass2026",
            })
            self.assertEqual(response.status_code, 401)
        limited = self.client.post_json(LOGIN_URL, {
            "email": "another@tongji.edu.cn", "password": "Wrong#Pass2026",
        })
        self.assertEqual(limited.status_code, 429)

    def test_register_failure_counts_toward_limit(self):
        """注册失败同样计数：连续失败注册后触发 429。"""
        for _ in range(5):
            response = self.client.post_json(REGISTER_URL, register_payload(password="1234567890"))
            self.assertEqual(response.status_code, 400)
        limited = self.client.post_json(REGISTER_URL, register_payload(password="1234567890"))
        self.assertEqual(limited.status_code, 429)

    def test_failure_keys_are_hashed(self):
        """计数键为摘要，不落明文邮箱。"""
        self.client.post_json(LOGIN_URL, {
            "email": self.user.email, "password": "Wrong#Pass2026",
        })
        for failure in AuthFailure.objects.all():
            self.assertEqual(len(failure.key_hash), 64)
            self.assertNotIn("@", failure.key_hash)


def clock_moment_after_window():
    from apps.core.clock import now

    return now() + ratelimit.WINDOW + timedelta(seconds=1)


class AdminCommandTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user(email="admin-candidate@tongji.edu.cn", password="Admin#Pass2026")
        self.user_audits = AuditLog.objects.filter(target_type="user", target_id=self.user.pk)
        self.client = CsrfFlowClient()

    def test_grant_and_revoke_admin_with_audit(self):
        """AT-02-05：授权/撤权受控且可审计；旧会话即时反映撤权。"""
        call_command("grant_admin", "--email", self.user.email, stdout=io.StringIO())
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_admin)
        self.assertEqual(self.user_audits.filter(action=actions.ADMIN_GRANT).count(), 1)

        self.client.post_json(LOGIN_URL, {
            "email": self.user.email, "password": "Admin#Pass2026",
        })
        self.assertTrue(self.client.get(ME_URL).data["data"]["is_admin"])

        call_command("revoke_admin", "--email", self.user.email, stdout=io.StringIO())
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_admin)
        self.assertTrue(self.user_audits.filter(action=actions.ADMIN_REVOKE).exists())
        self.assertFalse(self.client.get(ME_URL).data["data"]["is_admin"])

    def test_grant_revoke_idempotent_and_unknown_email(self):
        call_command("grant_admin", "--email", self.user.email, stdout=io.StringIO())
        call_command("grant_admin", "--email", self.user.email, stdout=io.StringIO())
        self.assertEqual(self.user_audits.filter(action=actions.ADMIN_GRANT).count(), 1)
        with self.assertRaisesMessage(CommandError, "账号不存在"):
            call_command("grant_admin", "--email", "missing@tongji.edu.cn", stdout=io.StringIO())

    def test_init_password_from_stdin(self):
        """AT-01-15：历史账号经受控命令初始化密码后可登录。"""
        unusable = make_user(email="legacy@tongji.edu.cn")
        self.assertFalse(unusable.has_usable_password())
        with mock.patch("sys.stdin", io.StringIO("Legacy#Init2026\n")):
            call_command("init_password", "--email", unusable.email, stdout=io.StringIO())
        unusable.refresh_from_db()
        self.assertTrue(unusable.has_usable_password())
        self.assertTrue(AuditLog.objects.filter(action=actions.PASSWORD_INIT).exists())
        response = self.client.post_json(LOGIN_URL, {
            "email": unusable.email, "password": "Legacy#Init2026",
        })
        self.assertEqual(response.status_code, 200)

        invalid = make_user(email="invalid-password@tongji.edu.cn")
        with mock.patch("sys.stdin", io.StringIO("12345678\n")):
            with self.assertRaisesMessage(CommandError, "密码不合规"):
                call_command("init_password", "--email", invalid.email, stdout=io.StringIO())
