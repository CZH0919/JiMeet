from django.http import Http404
from django.test import SimpleTestCase
from rest_framework import exceptions, status

from apps.core.errors import (
    ErrorCode,
    Forbidden,
    NotAuthenticated,
    NotFoundAsDenied,
    ValidationFailed,
)
from apps.core.exception_handler import handle


class ExceptionHandlerTest(SimpleTestCase):
    def _handle(self, exc):
        return handle(exc, {"request": None})

    def test_biz_error_envelope(self):
        response = self._handle(ValidationFailed(details={"title": "必填"}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], ErrorCode.VALIDATION_ERROR)
        self.assertEqual(response.data["data"], {"details": {"title": "必填"}})

    def test_drf_exceptions_mapped(self):
        cases = [
            (exceptions.NotAuthenticated(), ErrorCode.UNAUTHENTICATED, 401),
            (exceptions.AuthenticationFailed(), ErrorCode.AUTH_FAILED, 401),
            (exceptions.PermissionDenied(), ErrorCode.FORBIDDEN, 403),
            (exceptions.ValidationError({"a": ["必填"]}), ErrorCode.VALIDATION_ERROR, 400),
            (exceptions.ParseError(), ErrorCode.VALIDATION_ERROR, 400),
            (exceptions.MethodNotAllowed("GET"), ErrorCode.METHOD_NOT_ALLOWED, 405),
            (exceptions.NotFound(), ErrorCode.NOT_FOUND, 404),
            (Http404(), ErrorCode.NOT_FOUND, 404),
        ]
        for exc, code, http_status in cases:
            with self.subTest(exc=type(exc).__name__):
                response = self._handle(exc)
                self.assertEqual(response.status_code, http_status)
                self.assertEqual(response.data["code"], code)

    def test_validation_details_are_stringified(self):
        response = self._handle(exceptions.ValidationError({"a": ["必填"]}))
        self.assertEqual(response.data["data"], {"details": {"a": ["必填"]}})

    def test_unexpected_exception_hides_details(self):
        response = self._handle(RuntimeError("boom"))
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data["code"], ErrorCode.INTERNAL_ERROR)
        self.assertNotIn("boom", str(response.data))

    def test_denial_audit_failure_does_not_change_response(self):
        for exc in (Forbidden(), NotAuthenticated(), NotFoundAsDenied()):
            with self.subTest(exc=type(exc).__name__):
                response = self._handle(exc)
                self.assertIn(response.status_code, (401, 403, 404))
