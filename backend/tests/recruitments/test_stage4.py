"""招聘人数、删除入口和状态历史的一致性回归。"""
from datetime import timedelta
from unittest import mock

from apps.accounts.models import User
from apps.applications.models import ApplicationStatusHistory
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.core import clock
from apps.notifications.models import Notification
from apps.recruitments import services
from apps.recruitments.models import Recruitment
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_tag, make_user


class RecruitmentStage4Test(TxTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user()
        self.admin = make_user(is_admin=True)
        self.tag = make_tag()
        self.payload = {
            "title": "招聘规则验证", "type": "competition", "description": "需求说明",
            "tag_ids": [self.tag.pk], "min_headcount": 1, "max_headcount": 200,
            "deadline": (clock.now() + timedelta(days=30)).isoformat(),
        }

    def test_headcount_interval_and_strict_types(self):
        self.login(self.owner)
        created = self.client.post("/api/v1/recruitments", self.payload, format="json")
        self.assertEqual(created.status_code, 201)
        pk = created.data["data"]["id"]
        for fields in (
            {"max_headcount": 201}, {"max_headcount": 0}, {"max_headcount": True},
            {"max_headcount": 1.5}, {"max_headcount": "200"}, {"min_headcount": 201},
            {"min_headcount": 3, "max_headcount": 2},
        ):
            with self.subTest(fields=fields):
                response = self.client.patch(f"/api/v1/recruitments/{pk}", fields, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Recruitment.objects.get(pk=pk).max_headcount, 200)

    def test_description_length_and_active_tags(self):
        self.login(self.owner)
        for fields in ({"description": "文" * 5001}, {"tag_ids": []}, {"tag_ids": [self.tag.pk, self.tag.pk]}):
            with self.subTest(fields=list(fields)):
                response = self.client.post("/api/v1/recruitments", dict(self.payload, **fields), format="json")
                self.assertEqual(response.status_code, 400)
        self.tag.is_active = False
        self.tag.save(update_fields=["is_active"])
        self.assertEqual(self.client.post("/api/v1/recruitments", self.payload, format="json").status_code, 400)
        self.assertFalse(Recruitment.objects.exists())

    def test_reducing_limit_marks_full_and_records_automatic_rejection(self):
        r = make_recruitment(self.owner, min_headcount=1, accepted_count=1, max_headcount=200)
        accepted = make_application(r, make_user(), status="accepted")
        pending = make_application(r, make_user())
        self.login(self.owner)
        response = self.client.patch(f"/api/v1/recruitments/{r.pk}", {"max_headcount": 1}, format="json")
        self.assertEqual(response.status_code, 200)
        r.refresh_from_db(); pending.refresh_from_db(); accepted.refresh_from_db()
        self.assertEqual((r.status, r.accepted_count, pending.status, accepted.status), ("full", 1, "rejected", "accepted"))
        event = ApplicationStatusHistory.objects.get(application=pending)
        self.assertEqual((event.reason, event.actor_id, event.occurred_at), ("auto_full", None, r.full_at))

    def test_owner_and_governance_permissions_are_separate(self):
        self.owner.is_admin = True
        self.owner.save(update_fields=["is_admin"])
        now = clock.now()
        r = make_recruitment(self.owner, status="closed", closed_at=now, close_reason="manual")
        self.login(self.owner)
        detail = self.client.get(f"/api/v1/recruitments/{r.pk}").data["data"]
        self.assertFalse(detail["permissions"]["can_delete"])
        self.assertTrue(detail["permissions"]["can_govern_delete"])
        self.assertEqual(self.client.delete(f"/api/v1/recruitments/{r.pk}", {}, format="json").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/v1/admin/recruitments/{r.pk}", {}, format="json").status_code, 400)
        response = self.client.delete(f"/api/v1/admin/recruitments/{r.pk}", {"reason": "不合规内容"}, format="json")
        self.assertEqual(response.status_code, 200)
        notice = Notification.objects.get(type="admin_removed")
        self.assertIn("不合规内容", notice.content)
        self.assertEqual(notice.recipient_id, self.owner.pk)

    def test_admin_can_use_own_delete_without_governance_side_effects(self):
        r = make_recruitment(self.admin)
        self.login(self.admin)
        self.assertEqual(self.client.delete(f"/api/v1/recruitments/{r.pk}", {}, format="json").status_code, 200)
        self.assertEqual(AuditLog.objects.get(target_type="recruitment", target_id=r.pk).action, actions.RECRUITMENT_DELETE)
        self.assertFalse(Notification.objects.filter(type="admin_removed").exists())

    def test_other_admin_cannot_use_owner_delete_and_revocation_is_checked(self):
        r = make_recruitment(self.owner)
        self.login(self.admin)
        self.assertEqual(self.client.delete(f"/api/v1/recruitments/{r.pk}", {}, format="json").status_code, 403)
        User.objects.filter(pk=self.admin.pk).update(is_admin=False)
        from apps.core.errors import Forbidden

        with self.assertRaises(Forbidden):
            services.governance_delete_recruitment(self.admin, r.pk, reason="原因")
        r.refresh_from_db()
        self.assertIsNone(r.deleted_at)

    def test_deletion_zeroes_count_and_preserves_status_times(self):
        now = clock.now()
        r = make_recruitment(self.owner, accepted_count=1, max_headcount=1, status="full", full_at=now)
        accepted = make_application(r, make_user(), status="accepted", decided_at=now - timedelta(hours=1))
        rejected = make_application(r, make_user(), status="rejected")
        withdrawn = make_application(r, make_user(), status="withdrawn")
        decided = accepted.decided_at
        services.governance_delete_recruitment(self.admin, r.pk, reason="违规招聘")
        r.refresh_from_db(); accepted.refresh_from_db(); rejected.refresh_from_db(); withdrawn.refresh_from_db()
        self.assertEqual((r.accepted_count, r.status, r.full_at), (0, "full", now))
        self.assertEqual((accepted.status, accepted.decided_at), ("invalid", decided))
        self.assertEqual((rejected.status, withdrawn.status), ("rejected", "withdrawn"))
        event = ApplicationStatusHistory.objects.get(application=accepted)
        self.assertEqual((event.from_status, event.to_status, event.reason, event.actor_id), ("accepted", "invalid", "delete_invalid", self.admin.pk))
        self.login(self.admin)
        self.assertEqual(self.client.delete(f"/api/v1/admin/recruitments/{r.pk}", {"reason": "重复"}, format="json").status_code, 404)
        self.assertEqual(ApplicationStatusHistory.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action=actions.ADMIN_DELETE).count(), 1)

    def test_delete_audit_failure_rolls_back_all_side_effects(self):
        r = make_recruitment(self.owner, accepted_count=1)
        app = make_application(r, make_user(), status="accepted")
        with mock.patch("apps.recruitments.services.record", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                services.delete_recruitment(self.owner, r.pk)
        r.refresh_from_db(); app.refresh_from_db()
        self.assertEqual((r.deleted_at, r.accepted_count, app.status), (None, 1, "accepted"))
        self.assertFalse(ApplicationStatusHistory.objects.exists())
        self.assertFalse(Notification.objects.exists())
