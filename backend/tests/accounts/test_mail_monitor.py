"""验证码投递监控窗口、阈值、故障脱敏和代理来源的回归。"""
from datetime import timedelta
from io import StringIO
from smtplib import SMTPAuthenticationError
from unittest.mock import patch

from django.core.mail.backends.smtp import EmailBackend
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import RegistrationMailRequest
from apps.accounts.views import _client_ip
from apps.core import clock


@override_settings(
    REGISTRATION_FROM_EMAIL="sender@example.org", REGISTRATION_HMAC_KEY="x" * 32,
    MAILERS={"registration": {"BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                              "OPTIONS": {"host": "mail.example.org", "use_ssl": True,
                                          "username": "sender@example.org", "password": "test-only"}}},
)
class MailMonitorTest(TestCase):
    def test_completed_attempts_window_minimum_and_equal_threshold(self):
        now = clock.now()

        def sample(when, outcome):
            RegistrationMailRequest.objects.create(email_key="e" * 64, ip_key="a" * 64,
                                                   requested_at=when, delivered=outcome)

        with clock.freeze(now), patch.object(EmailBackend, "open", return_value=True), patch.object(
            EmailBackend, "send_messages", side_effect=AssertionError("监控不得发信")
        ):
            sample(now - timedelta(minutes=15), False)
            sample(now, None)
            for result in (True, True, True, False):
                sample(now, result)
            output = StringIO()
            call_command("check_registration_mail", stdout=output)
            self.assertIn("已完成 4 次，失败 1 次", output.getvalue())
            sample(now, True)
            with self.assertRaisesMessage(CommandError, "已完成 5 次，失败 1 次"):
                call_command("check_registration_mail")
            sample(now, True)
            call_command("check_registration_mail", stdout=StringIO())

    def test_smtp_outage_alerts_without_deliveries(self):
        with patch.object(EmailBackend, "open", side_effect=SMTPAuthenticationError(535, b"sensitive reply")):
            with self.assertRaises(CommandError) as err:
                call_command("check_registration_mail")
        self.assertIn("SMTPAuthenticationError", str(err.exception))
        self.assertNotIn("sensitive reply", str(err.exception))

    def test_missing_mailer_and_invalid_threshold(self):
        with self.assertRaises(CommandError):
            call_command("check_registration_mail", failure_percent=0)
        with override_settings(MAILERS={}), self.assertRaises(CommandError):
            call_command("check_registration_mail")


class ProxyClientAddressTest(SimpleTestCase):
    @override_settings(TRUST_HTTPS_PROXY=True)
    def test_unix_transport_uses_single_normalized_ip(self):
        factory = RequestFactory()
        for header, expected in [("2001:db8::0001", "2001:db8::1"), ("", "127.0.0.1"), ("invalid", "127.0.0.1")]:
            with self.subTest(ip=header):
                request = factory.get("/", REMOTE_ADDR="", HTTP_X_REAL_IP=header)
                self.assertEqual(_client_ip(request), expected)
        request = factory.get("/", REMOTE_ADDR="192.0.2.1", HTTP_X_REAL_IP="198.51.100.3")
        self.assertEqual(_client_ip(request), "192.0.2.1")

    @override_settings(TRUST_HTTPS_PROXY=False)
    def test_untrusted_header_is_ignored(self):
        self.assertEqual(_client_ip(RequestFactory().get("/", REMOTE_ADDR="", HTTP_X_REAL_IP="192.0.2.3")), "")
