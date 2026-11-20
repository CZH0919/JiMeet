"""注册验证码的会话约束、投递状态、发送额度及并发回归。"""
import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.core import mail
from django.db import close_old_connections, connections
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts import verification
from apps.accounts.models import RegistrationMailRequest, RegistrationVerification, User
from apps.accounts.services import register_with_password
from apps.core import clock
from apps.core.errors import BizError
from tests.accounts.test_auth import CsrfFlowClient, REGISTER_URL, SEND_CODE_URL, VERIFY_CODE_URL, VALID
from tests.base import TxTestCase
from tests.factories import make_user


class RegistrationVerificationTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.client = CsrfFlowClient()
        self.email = VALID["email"]

    def send(self, email=None):
        return self.client.post_json(SEND_CODE_URL, {"email": email or self.email})

    def verify(self, code, email=None, client=None):
        return (client or self.client).post_json(VERIFY_CODE_URL, {"email": email or self.email, "code": code})

    def test_fields_csrf_and_exact_domain(self):
        anonymous = APIClient(enforce_csrf_checks=True)
        for path, body in ((SEND_CODE_URL, {"email": self.email}), (VERIFY_CODE_URL, {"email": self.email, "code": "012345"})):
            self.assertEqual(anonymous.post(path, body, format="json").status_code, 403)
            self.assertEqual(self.client.post_json(path, dict(body, admin=True)).status_code, 400)
            form = self.client.post(path, body, format="multipart", HTTP_X_CSRFTOKEN=self.client.csrf_token)
            self.assertEqual((form.status_code, form["Cache-Control"]), (415, "private, no-store"))
        for email in ("x@sub.tongji.edu.cn", "x@tongji.edu.cn.example", "invalid"):
            self.assertEqual(self.send(email).status_code, 400)
        for code in (123456, "１２３４５６", " 123456", "12abc3"):
            self.assertEqual(self.verify(code).status_code, 400)
        self.assertFalse(RegistrationMailRequest.objects.exists())
        self.assertFalse(mail.outbox)

    def test_registered_address_same_receipt_without_delivery_or_grant(self):
        user = make_user(email="member@tongji.edu.cn", password="Member#2026!")
        first = self.send(user.email.upper())
        other = self.send()
        self.assertEqual((first.status_code, first.data["data"]), (other.status_code, other.data["data"]))
        self.assertEqual(other.data["data"], {"resend_after": 60, "expires_in": 600})
        self.assertEqual([m.to for m in mail.outbox], [[self.email]])
        self.assertEqual(self.send(user.email).status_code, 429)
        self.assertEqual(RegistrationVerification.objects.count(), 1)
        self.assertIsNone(user.email_verified_at)

    def test_session_email_and_code_are_bound(self):
        with patch("apps.accounts.verification.secrets.randbelow", return_value=39):
            code = self.client.delivered_code(self.email)
        self.assertEqual(code, "000039")
        row = RegistrationVerification.objects.get()
        self.assertNotEqual(row.code_digest, code)
        self.assertNotEqual(row.session_key_hash, self.client.session.session_key)
        self.assertEqual(len(row.email_key), 64)
        self.assertEqual(self.verify(code, client=CsrfFlowClient()).status_code, 400)
        self.assertEqual(self.verify(code, email="other@tongji.edu.cn").status_code, 400)
        self.assertEqual(self.client.post_json(REGISTER_URL, VALID).status_code, 400)
        result = self.verify(code)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["data"], {"expires_in": 600})
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertEqual(CsrfFlowClient().post_json(REGISTER_URL, VALID).status_code, 400)
        self.assertEqual(self.client.post_json(REGISTER_URL, dict(VALID, email="other@tongji.edu.cn")).status_code, 400)
        self.assertEqual(self.client.post_json(REGISTER_URL, dict(VALID, password="123456789")).status_code, 400)
        self.assertEqual(self.client.post_json(REGISTER_URL, VALID).status_code, 201)
        self.assertIsNotNone(User.objects.get().email_verified_at)
        self.assertFalse(RegistrationVerification.objects.exists())

    def test_fifth_wrong_code_invalidates_challenge(self):
        code = self.client.delivered_code(self.email)
        wrong = f"{(int(code) + 1) % 1_000_000:06d}"
        for _ in range(5):
            self.assertEqual(self.verify(wrong).status_code, 400)
        row = RegistrationVerification.objects.get()
        self.assertEqual((row.failures, row.code_digest), (5, ""))
        self.assertEqual(self.verify(code).status_code, 400)

    def test_expiry_boundaries_of_code_and_grant(self):
        start = clock.now()
        with self.freeze_at(start):
            code = self.client.delivered_code(self.email)
        with self.freeze_at(start + verification.CODE_TTL):
            self.assertEqual(self.verify(code).status_code, 400)
            self.client.verify_email(self.email)
        with self.freeze_at(start + verification.CODE_TTL + verification.GRANT_TTL):
            self.assertEqual(self.client.post_json(REGISTER_URL, VALID).status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_resend_cooldown_rotation_and_prior_grant(self):
        start = clock.now()
        with self.freeze_at(start), patch("apps.accounts.verification.secrets.randbelow", return_value=345678):
            first = self.client.delivered_code(self.email)
        with self.freeze_at(start + timedelta(seconds=59)):
            self.assertEqual(self.send().status_code, 429)
        with self.freeze_at(start + timedelta(seconds=60)), patch("apps.accounts.verification.secrets.randbelow", return_value=345678):
            second = self.client.delivered_code(self.email)
            self.assertNotEqual(first, second)
            self.assertEqual(self.verify(first).status_code, 400)
            self.assertEqual(self.verify(second).status_code, 200)
        with self.freeze_at(start + timedelta(seconds=120)):
            self.client.delivered_code(self.email)
            self.assertEqual(self.client.post_json(REGISTER_URL, VALID).status_code, 400)

    def test_smtp_failure_is_sanitized_and_reservation_is_counted(self):
        error = smtplib.SMTPAuthenticationError(535, b"private upstream diagnostic")
        with patch("apps.accounts.verification.send_mail", side_effect=error), self.assertLogs("apps.accounts.verification") as logs:
            response = self.send()
        self.assertEqual((response.status_code, response.data["code"]), (503, "EMAIL_DELIVERY_UNAVAILABLE"))
        exposed = response.content.decode() + str(logs.output)
        self.assertNotIn("private upstream diagnostic", exposed)
        self.assertNotIn(self.email, exposed)
        self.assertFalse(RegistrationVerification.objects.get().code_digest)
        self.assertEqual(self.send().status_code, 429)

    def test_failed_resend_keeps_previous_unexpired_code(self):
        start = clock.now()
        with self.freeze_at(start):
            code = self.client.delivered_code(self.email)
        with self.freeze_at(start + verification.RESEND_INTERVAL):
            with patch("apps.accounts.verification.send_mail", return_value=0):
                self.assertEqual(self.send().status_code, 503)
            self.assertEqual(self.verify(code).status_code, 200)

    def test_superseded_smtp_completion_cannot_reactivate_old_code(self):
        start = clock.now()
        session = self.client.session
        session[verification.SESSION_MARKER] = True
        session.save()
        codes = []

        def deliver(subject, body, sender, recipients, **kwargs):
            codes.append(body.split("验证码为 ")[1][:6])
            if len(codes) == 1:
                with self.freeze_at(start + verification.RESEND_INTERVAL):
                    verification.send_registration_code(email=self.email, ip="127.0.0.1", session=session)
            return 1

        with self.freeze_at(start), patch("apps.accounts.verification.send_mail", side_effect=deliver), patch(
            "apps.accounts.verification.secrets.randbelow", side_effect=[123456, 654321],
        ):
            verification.send_registration_code(email=self.email, ip="127.0.0.1", session=session)
        self.assertEqual(self.verify(codes[0]).status_code, 400)
        self.assertEqual(self.verify(codes[1]).status_code, 200)

    @override_settings(REGISTRATION_EMAIL_DAILY_LIMIT=1)
    def test_mailbox_daily_limit_and_expired_data_cleanup(self):
        start = clock.now()
        with self.freeze_at(start):
            self.client.verify_email(self.email)
            old_pk = RegistrationVerification.objects.get().pk
        with self.freeze_at(start + verification.RESEND_INTERVAL):
            self.assertEqual(self.send().status_code, 429)
        with self.freeze_at(start + verification.DAY):
            self.assertEqual(self.send().status_code, 200)
        self.assertEqual(RegistrationMailRequest.objects.count(), 1)
        self.assertFalse(RegistrationVerification.objects.filter(pk=old_pk).exists())

    @override_settings(REGISTRATION_IP_HOURLY_LIMIT=1, REGISTRATION_GLOBAL_DAILY_LIMIT=2)
    def test_ip_and_global_quotas_across_sessions(self):
        start = clock.now()
        with self.freeze_at(start):
            self.assertEqual(self.send().status_code, 200)
            self.client.defaults["HTTP_X_FORWARDED_FOR"] = "192.0.2.9"
            self.assertEqual(self.send("next@tongji.edu.cn").status_code, 429)
        with self.freeze_at(start + timedelta(hours=1)):
            self.assertEqual(self.send("next@tongji.edu.cn").status_code, 200)
            self.client.defaults["REMOTE_ADDR"] = "192.0.2.2"
            self.assertEqual(self.send("third@tongji.edu.cn").status_code, 429)

    @override_settings(REGISTRATION_HMAC_KEY="")
    def test_missing_hmac_key_fails_closed(self):
        self.assertEqual(self.send().status_code, 503)
        self.assertFalse(mail.outbox)


class RegistrationConcurrencyTest(TxTestCase):
    def race(self, action):
        gate = Barrier(2)

        def run():
            close_old_connections()
            try:
                gate.wait(timeout=8)
                return action()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(run) for _ in range(2)]
            return sorted(job.result(timeout=20) for job in jobs)

    def test_one_reservation_for_simultaneous_sends(self):
        def send():
            return CsrfFlowClient().post_json(SEND_CODE_URL, {"email": VALID["email"]}).status_code
        self.assertEqual(self.race(send), [200, 429])
        self.assertEqual((len(mail.outbox), RegistrationMailRequest.objects.count()), (1, 1))

    def test_one_verification_and_one_grant_consumption(self):
        client = CsrfFlowClient()
        code = client.delivered_code(VALID["email"])
        session_key = client.session.session_key

        def verify():
            try:
                verification.verify_registration_code(email=VALID["email"], code=code, session_key=session_key)
                return 200
            except BizError as exc:
                return exc.http_status

        def register():
            try:
                register_with_password(**VALID, session_key=session_key)
                return 201
            except BizError as exc:
                return exc.http_status

        self.assertEqual(self.race(verify), [200, 400])
        self.assertEqual(self.race(register), [201, 400])
        self.assertEqual(User.objects.count(), 1)
