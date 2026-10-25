from django.test import SimpleTestCase
from rest_framework import status

from apps.core.errors import (
    BizError,
    Conflict,
    ErrorCode,
    Forbidden,
    NotAuthenticated,
    NotFound,
    NotFoundAsDenied,
    ValidationFailed,
)


class ErrorCodeTest(SimpleTestCase):
    def test_covers_all_codes_from_plan_6_3(self):
        expected = {
            "OK",
            "UNAUTHENTICATED",
            "FORBIDDEN",
            "NOT_FOUND",
            "VALIDATION_ERROR",
            "PRIVACY_NOT_CONSENTED",
            "SELF_APPLICATION_FORBIDDEN",
            "RECRUITMENT_NOT_OPEN",
            "RECRUITMENT_NOT_EDITABLE",
            "RECRUITMENT_FULL",
            "PROCESSING_WINDOW_CLOSED",
            "HEADCOUNT_BELOW_ACCEPTED",
            "DUPLICATE_APPLICATION",
            "APPLICATION_NOT_PROCESSING",
            "INVALID_RESUME_FILE",
            "AUTH_FAILED",
            "SSO_UNAVAILABLE",
            "INTERNAL_ERROR",
        }
        actual = {value for name, value in vars(ErrorCode).items() if name.isupper()}
        self.assertTrue(expected.issubset(actual), expected - actual)


class BizErrorTest(SimpleTestCase):
    def test_subclass_defaults(self):
        cases = [
            (NotAuthenticated(), ErrorCode.UNAUTHENTICATED, status.HTTP_401_UNAUTHORIZED),
            (Forbidden(), ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN),
            (NotFound(), ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND),
            (ValidationFailed(), ErrorCode.VALIDATION_ERROR, status.HTTP_400_BAD_REQUEST),
            (NotFoundAsDenied(), ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND),
        ]
        for exc, code, http_status in cases:
            with self.subTest(exc=type(exc).__name__):
                self.assertEqual(exc.code, code)
                self.assertEqual(exc.http_status, http_status)
                self.assertTrue(exc.message)

    def test_conflict_requires_code(self):
        with self.assertRaises(ValueError):
            Conflict("")
        exc = Conflict(ErrorCode.RECRUITMENT_FULL, "已满员")
        self.assertEqual(exc.code, ErrorCode.RECRUITMENT_FULL)
        self.assertEqual(exc.http_status, status.HTTP_409_CONFLICT)
        self.assertEqual(exc.message, "已满员")

    def test_details_and_audit_target(self):
        exc = ValidationFailed(details={"title": "必填"}, audit_target=("recruitment", 7))
        self.assertEqual(exc.details, {"title": "必填"})
        self.assertEqual(exc.audit_target, ("recruitment", 7))

    def test_base_error_defaults_to_internal(self):
        exc = BizError()
        self.assertEqual(exc.code, ErrorCode.INTERNAL_ERROR)
        self.assertEqual(exc.http_status, status.HTTP_500_INTERNAL_SERVER_ERROR)
