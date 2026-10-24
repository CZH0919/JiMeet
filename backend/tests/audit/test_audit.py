from django.db import transaction
from rest_framework import exceptions

from apps.audit import actions
from apps.audit.models import AuditLog
from apps.audit.service import record
from apps.core.errors import Forbidden, NotAuthenticated, NotFoundAsDenied
from apps.core.exception_handler import handle
from tests.base import TxTestCase
from tests.factories import make_user


class AuditTest(TxTestCase):
    def test_actor_snapshot_and_reason_limit(self):
        actor = make_user(role="teacher", is_admin=True)
        with transaction.atomic():
            log = record(actor=actor, action=actions.ADMIN_DELETE, target_type="recruitment",
                         target_id=10, reason="因" * 501)
        actor.role = "student"
        actor.is_admin = False
        actor.save(update_fields=["role", "is_admin"])
        log.refresh_from_db()
        self.assertEqual((log.actor_role, log.actor_is_admin, len(log.reason)), ("teacher", True, 500))
        with self.assertRaises(RuntimeError):
            log.save()
        with self.assertRaises(RuntimeError):
            log.delete()

    def test_anonymous_denial_and_required_fields(self):
        log = record(actor=None, action=actions.PERMISSION_DENIED, target_type="request", target_id=None)
        self.assertEqual((log.actor_id, log.actor_role, log.actor_is_admin), (None, None, None))
        for fields in (
            dict(actor=None, action=actions.RECRUITMENT_DELETE, target_type="recruitment", target_id=1),
            dict(actor=None, action=actions.PERMISSION_DENIED, target_type=" ", target_id=None),
            dict(actor=None, action="unknown_action", target_type="request", target_id=None),
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                record(**fields)

    def test_admin_delete_requires_reason(self):
        actor = make_user(role="teacher", is_admin=True)
        for reason in (None, "", "  "):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                record(actor=actor, action=actions.ADMIN_DELETE, target_type="recruitment",
                       target_id=1, reason=reason)
        self.assertEqual(AuditLog.objects.count(), 0)
        log = record(actor=actor, action=actions.ADMIN_DELETE, target_type="recruitment",
                     target_id=1, reason="违规内容")
        self.assertEqual(log.reason, "违规内容")
        # 其他动作不强制原因。
        self.assertIsNone(record(actor=actor, action=actions.RESUME_VIEW,
                                 target_type="application", target_id=2).reason)

    def test_handler_records_business_and_drf_denials(self):
        for exc in (Forbidden(), NotAuthenticated(), NotFoundAsDenied(),
                    exceptions.NotAuthenticated(), exceptions.PermissionDenied()):
            with self.subTest(exc=type(exc).__name__):
                before = AuditLog.objects.count()
                handle(exc, {"request": None})
                self.assertEqual(AuditLog.objects.count(), before + 1)
        actor = make_user()
        request = type("Request", (), {"user": actor})()
        response = handle(Forbidden(audit_target=("application", 12)), {"request": request})
        self.assertEqual(response.status_code, 403)
        log = AuditLog.objects.latest("pk")
        self.assertEqual((log.actor_id, log.target_type, log.target_id), (actor.pk, "application", 12))

    def test_business_rollback_also_rolls_back_audit(self):
        actor = make_user()
        with self.assertRaises(ValueError), transaction.atomic():
            record(actor=actor, action=actions.APPLICATION_UPDATE, target_type="application", target_id=1)
            raise ValueError("rollback")
        self.assertEqual(AuditLog.objects.count(), 0)
