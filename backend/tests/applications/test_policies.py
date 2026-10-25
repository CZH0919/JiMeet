from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.applications.policies import (
    can_modify_application, can_process_application, can_submit_application,
    can_withdraw_application, resolve_application_access,
)
from apps.core.errors import BizError, ErrorCode


class ApplicationPoliciesTest(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.publisher = SimpleNamespace(pk=1, is_authenticated=True, is_admin=False, privacy_consented_at=self.now)
        self.applicant = SimpleNamespace(pk=2, is_authenticated=True, is_admin=False, privacy_consented_at=self.now)
        self.admin = SimpleNamespace(pk=3, is_authenticated=True, is_admin=True, privacy_consented_at=self.now)
        self.stranger = SimpleNamespace(pk=4, is_authenticated=True, is_admin=False, privacy_consented_at=self.now)
        self.anonymous = SimpleNamespace(pk=None, is_authenticated=False, is_admin=False, privacy_consented_at=None)
        self.r = SimpleNamespace(
            publisher_id=1, deadline=self.now + timedelta(days=1),
            status="open", closed_at=None, full_at=None, deleted_at=None,
        )
        self.app = SimpleNamespace(pk=1, applicant_id=2, status="processing")

    def test_submit_requires_login(self):
        with self.assertRaises(BizError) as caught:
            can_submit_application(self.anonymous, self.r, self.now, has_active_application=False)
        self.assertEqual(caught.exception.code, ErrorCode.UNAUTHENTICATED)

    def test_access_table(self):
        for status in ("processing", "accepted", "rejected", "withdrawn", "invalid"):
            restricted = status in {"withdrawn", "invalid"}
            self.app.status = status
            for user, relation, expected in (
                (self.admin, "none", (False, False, False, False, False)),
                (self.stranger, "none", (False, False, False, False, False)),
                (self.anonymous, "none", (False, False, False, False, False)),
                (self.applicant, "applicant", (True, True, False, not restricted, False)),
                (self.publisher, "publisher", (True, not restricted, True, not restricted, not restricted)),
            ):
                with self.subTest(status=status, relation=relation):
                    access = resolve_application_access(user, self.app, self.r, self.now)
                    self.assertEqual(access.relation, relation)
                    self.assertEqual((access.can_view, access.can_see_note, access.can_see_applicant_name,
                                      access.can_download_resume, access.can_see_publisher_mark), expected)
        self.r.full_at = self.now - timedelta(days=180)
        for user, relation in ((self.publisher, "publisher"), (self.applicant, "applicant")):
            access = resolve_application_access(user, self.app, self.r, self.now)
            self.assertEqual(access.relation, relation)
            self.assertFalse(any((access.can_view, access.can_see_note, access.can_see_applicant_name,
                                  access.can_download_resume, access.can_see_publisher_mark)))

    def test_same_user_falls_back_to_publisher(self):
        self.app.applicant_id = self.publisher.pk
        with self.assertLogs("apps.applications.policies", level="ERROR"):
            access = resolve_application_access(self.publisher, self.app, self.r, self.now)
        self.assertEqual(access.relation, "publisher")

    def test_submit_rejections_in_order(self):
        self.r.status = "closed"
        self.publisher.privacy_consented_at = None
        self.applicant.privacy_consented_at = None
        cases = (
            (self.publisher, ErrorCode.SELF_APPLICATION_FORBIDDEN),
            (self.applicant, ErrorCode.PRIVACY_NOT_CONSENTED),
            (self.admin, ErrorCode.RECRUITMENT_NOT_OPEN),
        )
        for user, code in cases:
            with self.subTest(code=code), self.assertRaises(BizError) as caught:
                can_submit_application(user, self.r, self.now, has_active_application=True)
            self.assertEqual(caught.exception.code, code)
        self.r.status = "open"
        with self.assertRaises(BizError) as caught:
            can_submit_application(self.admin, self.r, self.now, has_active_application=True)
        self.assertEqual(caught.exception.code, ErrorCode.DUPLICATE_APPLICATION)
        can_submit_application(self.admin, self.r, self.now, has_active_application=False)

    def test_operation_permissions(self):
        for check in (can_modify_application, can_withdraw_application):
            self.assertTrue(check(self.applicant, self.app, self.r))
            self.assertFalse(check(self.admin, self.app, self.r))
        self.assertTrue(can_process_application(self.publisher, self.app, self.r, self.now))
        self.assertFalse(can_process_application(self.admin, self.app, self.r, self.now))
        self.r.status = "closed"
        self.r.closed_at = self.now - timedelta(days=7)
        self.assertFalse(can_process_application(self.publisher, self.app, self.r, self.now))
        self.assertTrue(can_modify_application(self.applicant, self.app, self.r))
        self.app.status = "accepted"
        self.assertFalse(can_modify_application(self.applicant, self.app, self.r))
        self.assertFalse(can_process_application(self.publisher, self.app, self.r, self.now))
        self.app.status = "processing"
        self.r.deleted_at = self.now
        self.assertFalse(can_withdraw_application(self.applicant, self.app, self.r))
