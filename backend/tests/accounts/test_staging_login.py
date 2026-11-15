from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory
from apps.accounts.login_policy import development_login_enabled
from apps.accounts.views import DevLoginView
from apps.accounts.models import User
from apps.audit.models import AuditLog


class StagingLoginTests(TestCase):
    @override_settings(DEBUG=False, ALLOW_DEV_LOGIN=True, STAGING_LOGIN_ENABLED=False)
    def test_production_debug_off_does_not_expose_login(self):
        self.assertFalse(development_login_enabled())

    @override_settings(DEBUG=False, ALLOW_DEV_LOGIN=True, STAGING_LOGIN_ENABLED=True,
                       STAGING_LOGIN_IDS=["qa01"])
    def test_staging_rejects_unknown_identity_without_creating_account(self):
        self.assertTrue(development_login_enabled())
        request = APIRequestFactory().post("/api/v1/auth/dev-login", {"real_id": "outsider"}, format="json")
        response = DevLoginView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(real_id="outsider").exists())
        self.assertEqual(AuditLog.objects.count(), 1)

    @override_settings(DEBUG=False, ALLOW_DEV_LOGIN=True, STAGING_LOGIN_ENABLED=True,
                       STAGING_LOGIN_IDS=["qa01"])
    def test_staging_still_requires_csrf(self):
        request = APIRequestFactory(enforce_csrf_checks=True).post(
            "/api/v1/auth/dev-login", {"real_id": "qa01"}, format="json")
        response = DevLoginView.as_view()(request)
        self.assertEqual(response.status_code, 403)
