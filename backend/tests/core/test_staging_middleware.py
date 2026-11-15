from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase
from apps.core.staging_middleware import StagingSessionStatusMiddleware


class StagingSessionStatusTests(SimpleTestCase):
    def test_missing_session_preserves_error_body_without_challenging_gateway_login(self):
        response = JsonResponse({'code': 'UNAUTHENTICATED', 'data': None}, status=401)
        response['WWW-Authenticate'] = 'Session'
        original = response.content
        result = StagingSessionStatusMiddleware(lambda _: response)(RequestFactory().get('/api/v1/me'))
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.content, original)
        self.assertNotIn('WWW-Authenticate', result)
        self.assertEqual(result['Cache-Control'], 'no-store')

    def test_does_not_change_other_statuses_or_non_api_responses(self):
        for path, status in [('/api/v1/me', 200), ('/api/v1/me', 403), ('/api/v1/me', 500), ('/other', 401)]:
            with self.subTest(path=path, status=status):
                response = JsonResponse({}, status=status)
                result = StagingSessionStatusMiddleware(lambda _: response)(RequestFactory().get(path))
                self.assertEqual(result.status_code, status)
