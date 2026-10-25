from unittest import mock

from django.test import TestCase

from apps.core.errors import ErrorCode


class HealthzTest(TestCase):
    def test_ok(self):
        response = self.client.get("/api/v1/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], ErrorCode.OK)
        self.assertEqual(response.json()["data"], {"status": "ok"})
        self.assertIn("X-Request-Id", response)

    def test_database_failure_returns_503(self):
        with mock.patch("apps.core.health.connection.cursor", side_effect=RuntimeError("down")):
            response = self.client.get("/api/v1/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], ErrorCode.INTERNAL_ERROR)

    def test_no_login_required(self):
        response = self.client.get("/api/v1/healthz")
        self.assertNotEqual(response.status_code, 401)
