from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.models import User
from apps.announcements import selectors, services
from apps.announcements.models import Announcement
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.core.clock import now
from apps.core.errors import Forbidden, NotFound
from apps.notifications import types
from apps.notifications.models import Notification
from tests.base import TxTestCase
from tests.factories import make_recruitment, make_user


def _create(actor, **overrides):
    fields = {
        "actor": actor,
        "title": "公告",
        "content": "正文",
        "time_kind": "deadline",
        "event_at": now() + timedelta(days=3),
    }
    fields.update(overrides)
    return services.create_announcement(**fields)


def _ids():
    return [a.pk for a in selectors.list_announcements()]


class AnnouncementTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user(is_admin=True)

    def test_create_with_optional_fields_and_audit(self):
        recruitment = make_recruitment(make_user())
        a = _create(self.admin, link_url="https://example.com", recruitment=recruitment)
        a.refresh_from_db()
        self.assertEqual(
            (a.recruitment_id, a.link_url, a.is_pinned),
            (recruitment.pk, "https://example.com", False),
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action=actions.ANNOUNCEMENT_PUBLISH, target_id=a.pk, actor=self.admin
            ).exists()
        )
        plain = _create(self.admin)
        self.assertIsNone(plain.recruitment_id)
        self.assertIsNone(plain.link_url)

    def test_create_requires_current_admin(self):
        revoked = make_user(is_admin=True)
        User.objects.filter(pk=revoked.pk).update(is_admin=False)
        with self.assertRaises(Forbidden):
            _create(revoked, title="撤权后发布")
        self.assertEqual(Announcement.objects.count(), 0)

    def test_time_kind_check_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Announcement.objects.create(
                author=self.admin, title="x", content="y", time_kind="bad", event_at=now()
            )

    def test_event_at_is_required(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Announcement.objects.create(
                author=self.admin, title="x", content="y", time_kind="event", event_at=None
            )

    def test_list_order_is_created_at_desc_ignoring_pin(self):
        first = _create(self.admin, title="first")
        second = _create(self.admin, title="second")
        third = _create(self.admin, title="third")
        self.assertEqual(_ids(), [third.pk, second.pk, first.pk])
        # HTTP 不按置顶排序：置顶不改变顺序
        services.update_announcement(first.pk, actor=self.admin, is_pinned=True)
        self.assertEqual(_ids(), [third.pk, second.pk, first.pk])
        services.update_announcement(first.pk, actor=self.admin, is_pinned=False)
        self.assertEqual(_ids(), [third.pk, second.pk, first.pk])
        self.assertEqual(
            AuditLog.objects.filter(action=actions.ANNOUNCEMENT_UPDATE).count(), 2
        )

    def test_update_changes_fields(self):
        a = _create(self.admin)
        services.update_announcement(a.pk, actor=self.admin, title="新标题", time_kind="event")
        a.refresh_from_db()
        self.assertEqual((a.title, a.time_kind), ("新标题", "event"))
        self.assertFalse(a.is_pinned)
        self.assertTrue(
            AuditLog.objects.filter(action=actions.ANNOUNCEMENT_UPDATE, target_id=a.pk).exists()
        )

    def test_repeated_updates_keep_last_value_and_each_is_audited(self):
        a = _create(self.admin, title="v0")
        previous = a.updated_at
        for i in range(1, 6):
            services.update_announcement(a.pk, actor=self.admin, title=f"v{i}")
            a.refresh_from_db()
            self.assertEqual(a.title, f"v{i}")
            self.assertGreater(a.updated_at, previous)
            previous = a.updated_at
        self.assertEqual(
            AuditLog.objects.filter(action=actions.ANNOUNCEMENT_UPDATE, target_id=a.pk).count(),
            5,
        )

    def test_update_rejects_unknown_fields_and_changes_nothing(self):
        a = _create(self.admin, title="原标题")
        other = make_user(is_admin=True)
        for bad in ({"author": other}, {"deleted_at": now()}, {"id": 999}):
            with self.assertRaises(ValueError):
                services.update_announcement(a.pk, actor=self.admin, title="不应保存", **bad)
        a.refresh_from_db()
        self.assertEqual((a.title, a.author_id, a.deleted_at), ("原标题", self.admin.pk, None))
        self.assertFalse(
            AuditLog.objects.filter(action=actions.ANNOUNCEMENT_UPDATE, target_id=a.pk).exists()
        )

    def test_update_can_set_and_clear_recruitment_and_link(self):
        recruitment = make_recruitment(make_user())
        a = _create(self.admin)
        services.update_announcement(
            a.pk, actor=self.admin, recruitment=recruitment, link_url="https://a.example"
        )
        a.refresh_from_db()
        self.assertEqual((a.recruitment_id, a.link_url), (recruitment.pk, "https://a.example"))
        services.update_announcement(a.pk, actor=self.admin, recruitment=None, link_url=None)
        a.refresh_from_db()
        self.assertEqual((a.recruitment_id, a.link_url), (None, None))

    def test_update_requires_author(self):
        a = _create(self.admin)
        other_admin = make_user(is_admin=True)
        with self.assertRaises(Forbidden):
            services.update_announcement(a.pk, actor=other_admin, title="越权修改")
        a.refresh_from_db()
        self.assertEqual(a.title, "公告")

    def test_revoked_admin_cannot_update_or_delete(self):
        revoked = make_user(is_admin=True)
        a = _create(revoked)
        User.objects.filter(pk=revoked.pk).update(is_admin=False)
        for call in (
            lambda: services.update_announcement(a.pk, actor=revoked, title="x"),
            lambda: services.soft_delete_announcement(a.pk, actor=revoked),
            lambda: services.governance_delete_announcement(a.pk, actor=revoked, reason="r"),
            lambda: services.create_announcement(
                actor=revoked, title="t", content="c", time_kind="event", event_at=now()
            ),
        ):
            with self.subTest(), self.assertRaises(Forbidden):
                call()
        self.assertIsNotNone(selectors.get_announcement(a.pk))

    def test_self_soft_delete_hides_without_reason_or_notification(self):
        a = _create(self.admin)
        services.soft_delete_announcement(a.pk, actor=self.admin)
        self.assertEqual(_ids(), [])
        self.assertIsNone(selectors.get_announcement(a.pk))
        self.assertTrue(Announcement.objects.filter(pk=a.pk).exists())
        log = AuditLog.objects.get(action=actions.ANNOUNCEMENT_DELETE)
        self.assertIsNone(log.reason)
        self.assertEqual(Notification.objects.count(), 0)

    def test_governance_delete_with_reason_notifies_author(self):
        other_admin = make_user(is_admin=True)
        a = _create(self.admin)
        services.governance_delete_announcement(a.pk, actor=other_admin, reason="内容过期")
        self.assertEqual(_ids(), [])
        log = AuditLog.objects.get(action=actions.ANNOUNCEMENT_DELETE)
        self.assertEqual((log.reason, log.actor_id), ("内容过期", other_admin.pk))
        notice = Notification.objects.get(type=types.ANNOUNCEMENT_ADMIN_REMOVED)
        self.assertEqual((notice.recipient_id, notice.announcement_id), (self.admin.pk, a.pk))
        self.assertIn("公告", notice.content)
        self.assertIn("内容过期", notice.content)

    def test_repeated_delete_returns_not_found_without_duplicate_side_effects(self):
        a = _create(self.admin)
        services.soft_delete_announcement(a.pk, actor=self.admin)
        for call in (
            lambda: services.soft_delete_announcement(a.pk, actor=self.admin),
            lambda: services.governance_delete_announcement(a.pk, actor=self.admin, reason="重复"),
        ):
            with self.subTest(), self.assertRaises(NotFound):
                call()
        self.assertEqual(AuditLog.objects.filter(action=actions.ANNOUNCEMENT_DELETE).count(), 1)
        self.assertEqual(Notification.objects.count(), 0)

    def test_update_after_delete_race_rejects(self):
        a = _create(self.admin)
        services.governance_delete_announcement(a.pk, actor=self.admin, reason="先行删除")
        with self.assertRaises(NotFound):
            services.update_announcement(a.pk, actor=self.admin, title="删除后更新")
        a.refresh_from_db()
        self.assertEqual(a.title, "公告")

    def test_get_announcement(self):
        a = _create(self.admin)
        self.assertEqual(selectors.get_announcement(a.pk).pk, a.pk)
        self.assertIsNone(selectors.get_announcement(a.pk + 999))

    def test_recruitment_is_protected(self):
        recruitment = make_recruitment(make_user())
        _create(self.admin, recruitment=recruitment)
        with self.assertRaises(ProtectedError):
            recruitment.delete()
