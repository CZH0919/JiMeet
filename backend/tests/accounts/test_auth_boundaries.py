"""注册、登录输入校验与失败计数的一致性回归。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import close_old_connections, connections

from apps.accounts import ratelimit
from apps.accounts.models import AuthFailure, User
from apps.accounts.services import register_with_password
from apps.core import clock
from apps.core.errors import BizError
from tests.accounts.test_auth import CsrfFlowClient
from tests.base import TxTestCase
from tests.factories import make_user


class AuthInputBoundaryTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.client = CsrfFlowClient()
        self.payload = {"email": "boundary@tongji.edu.cn", "name": "审查用户", "password": "BoundaryPass!4827"}

    def test_registration_rejects_password_similar_to_name_or_email(self):
        for overrides in (
            {"name": "CedarRiver!5928", "password": "CedarRiver!5928"},
            {"email": "similarperson4827@tongji.edu.cn", "password": "similarperson4827"},
        ):
            with self.subTest(fields=sorted(overrides)):
                response = self.client.post_json("/api/v1/auth/register", dict(self.payload, **overrides))
                self.assertEqual(response.status_code, 400)
                self.assertFalse(User.objects.exists())

    def test_registration_password_length_boundaries(self):
        for index, (password, expected) in enumerate((
            ("Ax!2937", 400), ("Ax!2937Q", 201), ("Az!79" * 25 + "Qx8", 201), ("Az!79" * 25 + "Qx89", 400),
        )):
            with self.subTest(length=len(password)):
                response = self.client.post_json("/api/v1/auth/register", dict(
                    self.payload, email=f"length{index}@tongji.edu.cn", password=password,
                ))
                self.assertEqual(response.status_code, expected)

    def test_field_and_business_failures_are_counted_once(self):
        make_user(email=self.payload["email"])
        for changes in ({"password": "short"}, {"is_admin": True}, {"password": "1234567890"}, {}):
            with self.subTest(fields=sorted(changes)):
                AuthFailure.objects.all().delete()
                response = self.client.post_json("/api/v1/auth/register", dict(self.payload, **changes))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(AuthFailure.objects.filter(kind=ratelimit.KIND_REGISTER).count(), 2)

    def test_invalid_email_uses_ip_limit_without_email_key(self):
        for index in range(21):
            response = self.client.post_json("/api/v1/auth/register", dict(self.payload, email="invalid"))
            self.assertEqual(response.status_code, 400 if index < 20 else 429)
        self.assertEqual(AuthFailure.objects.count(), 20)
        self.assertEqual(AuthFailure.objects.values("key_hash").distinct().count(), 1)

    def test_malformed_json_and_non_mapping_inputs_are_counted_by_ip(self):
        for body in ("{", "[]", "null"):
            with self.subTest(body=body):
                AuthFailure.objects.all().delete()
                response = self.client.post(
                    "/api/v1/auth/register", data=body, content_type="application/json",
                    HTTP_X_CSRFTOKEN=self.client.csrf_token,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(AuthFailure.objects.count(), 1)

    def test_normalized_email_limit_survives_ip_changes_and_recovers(self):
        moment = clock.now()
        with self.freeze_at(moment):
            for index in range(6):
                self.client.defaults["REMOTE_ADDR"] = f"192.0.2.{index + 1}"
                response = self.client.post_json("/api/v1/auth/register", dict(
                    self.payload, email=" BOUNDARY@Tongji.Edu.Cn ", password="short",
                ))
                self.assertEqual(response.status_code, 400 if index < 5 else 429)
        with self.freeze_at(moment + ratelimit.WINDOW + timedelta(seconds=1)):
            self.assertEqual(self.client.post_json("/api/v1/auth/register", self.payload).status_code, 201)
        self.assertFalse(AuthFailure.objects.filter(
            key_hash=ratelimit._key_hash("email", self.payload["email"]), kind=ratelimit.KIND_REGISTER,
        ).exists())

    def test_registration_and_login_limits_are_independent(self):
        make_user(email=self.payload["email"], password=self.payload["password"])
        for _ in range(5):
            self.assertEqual(self.client.post_json("/api/v1/auth/register", self.payload).status_code, 400)
        self.assertEqual(self.client.post_json("/api/v1/auth/register", self.payload).status_code, 429)
        self.assertEqual(self.client.post_json("/api/v1/auth/login", {
            "email": self.payload["email"], "password": self.payload["password"],
        }).status_code, 200)

    def test_login_field_failure_is_counted_without_creating_session(self):
        for index in range(6):
            response = self.client.post_json("/api/v1/auth/login", {
                "email": self.payload["email"], "password": "",
            })
            self.assertEqual(response.status_code, 400 if index < 5 else 429)
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)

    def test_concurrent_failure_records_are_not_lost(self):
        gate = Barrier(5)

        def fail():
            close_old_connections()
            try:
                gate.wait(timeout=10)
                ratelimit.record_auth_failure(email=self.payload["email"], ip="192.0.2.1", kind=ratelimit.KIND_REGISTER)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(fail) for _ in range(5)]
            for future in futures:
                future.result(timeout=20)
        self.assertEqual(AuthFailure.objects.count(), 10)

    def test_concurrent_registration_preserves_email_uniqueness(self):
        gate = Barrier(2)

        def register():
            close_old_connections()
            try:
                gate.wait(timeout=10)
                register_with_password(**self.payload)
                return 201
            except BizError as error:
                return error.http_status
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(register) for _ in range(2)]
            self.assertEqual(sorted(future.result(timeout=20) for future in futures), [201, 400])
        self.assertEqual(User.objects.filter(email=self.payload["email"]).count(), 1)
