from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.announcements import selectors, services
from apps.announcements.models import Announcement
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.core.clock import now
from tests.base import TxTestCase
from tests.factories import make_recruitment, make_user


def _create(author, **overrides):
    fields = {
        "author": author,
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

    def test_list_order_newest_first_and_pinned_first(self):
        first = _create(self.admin, title="first")
        second = _create(self.admin, title="second")
        third = _create(self.admin, title="third")
        self.assertEqual(_ids(), [third.pk, second.pk, first.pk])
        services.update_announcement(first, actor=self.admin, is_pinned=True)
        self.assertEqual(_ids(), [first.pk, third.pk, second.pk])
        services.update_announcement(first, actor=self.admin, is_pinned=False)
        self.assertEqual(_ids(), [third.pk, second.pk, first.pk])
        # 置顶与编辑共用 announcement_update 审计：共 2 次置顶变更
        self.assertEqual(
     AuditLog.objects.filter(action=actions.ANNOUNCEMENT_UPDATE).count(), 2
 )

    def test_update_changes_fields(self):
        a = _create(self.admin)
        services.update_announcement(a, actor=self.admin, title="新标题", time_kind="event")
        a.refresh_from_db()
        self.assertEqual((a.title, a.time_kind), ("新标题", "event"))
        self.assertFalse(a.is_pinned)
        self.assertTrue(
            AuditLog.objects.filter(action=actions.ANNOUNCEMENT_UPDATE, target_id=a.pk).exists()
        )

    def test_update_can_change_pin_together_with_other_fields(self):
        a = _create(self.admin)
        services.update_announcement(a, actor=self.admin, title="置顶公告", is_pinned=True)
        a.refresh_from_db()
        self.assertEqual((a.title, a.is_pinned), ("置顶公告", True))
        services.update_announcement(a, actor=self.admin, is_pinned=False)
        a.refresh_from_db()
        self.assertEqual((a.title, a.is_pinned), ("置顶公告", False))

    def test_repeated_updates_keep_last_value_and_each_is_audited(self):
        a = _create(self.admin, title="v0")
        previous = a.updated_at
        for i in range(1, 6):
            services.update_announcement(
                a, actor=self.admin, title=f"v{i}", is_pinned=(i % 2 == 1)
            )
            a.refresh_from_db()
            self.assertEqual((a.title, a.is_pinned), (f"v{i}", i % 2 == 1))
            self.assertGreater(a.updated_at, previous)
            previous = a.updated_at
        # 5 次修改后标题为 v5，奇数次置顶，所以最终仍为置顶
        self.assertTrue(a.is_pinned)
        self.assertEqual(
            AuditLog.objects.filter(action=actions.ANNOUNCEMENT_UPDATE, target_id=a.pk).count(),
            5,
        )

    def test_repeated_same_value_update_is_idempotent(self):
        a = _create(self.admin)
        for _ in range(3):
            services.update_announcement(a, actor=self.admin, title="同一标题", is_pinned=True)
        a.refresh_from_db()
        self.assertEqual((a.title, a.is_pinned), ("同一标题", True))
        self.assertEqual(_ids(), [a.pk])

    def test_multiple_pinned_sorted_by_created_at_desc(self):
        first = _create(self.admin, title="first")
        second = _create(self.admin, title="second")
        third = _create(self.admin, title="third")
        services.update_announcement(first, actor=self.admin, is_pinned=True)
        self.assertEqual(_ids(), [first.pk, third.pk, second.pk])
               # 再置顶第二条：两条置顶之间按发布时间倒序
        services.update_announcement(second, actor=self.admin, is_pinned=True)
        self.assertEqual(_ids(), [second.pk, first.pk, third.pk])
               # 全部取消置顶后回到纯发布时间倒序
        services.update_announcement(first, actor=self.admin, is_pinned=False)
        services.update_announcement(second, actor=self.admin, is_pinned=False)
        self.assertEqual(_ids(), [third.pk, second.pk, first.pk])

    def test_update_rejects_unknown_fields_and_changes_nothing(self):
        a = _create(self.admin, title="原标题")
        other = make_user(is_admin=True)
        for bad in ({"author": other}, {"deleted_at": now()}, {"id": 999}):
            with self.assertRaises(ValueError):
                services.update_announcement(a, actor=self.admin, title="不应保存", **bad)
        a.refresh_from_db()
        self.assertEqual((a.title, a.author_id, a.deleted_at), ("原标题", self.admin.pk, None))
        self.assertFalse(
            AuditLog.objects.filter(action=actions.ANNOUNCEMENT_UPDATE, target_id=a.pk).exists()
        )

    def test_update_can_set_and_clear_recruitment_and_link(self):
        recruitment = make_recruitment(make_user())
        a = _create(self.admin)
        services.update_announcement(
            a, actor=self.admin, recruitment=recruitment, link_url="https://a.example"
        )
        a.refresh_from_db()
        self.assertEqual((a.recruitment_id, a.link_url), (recruitment.pk, "https://a.example"))
        services.update_announcement(a, actor=self.admin, recruitment=None, link_url=None)
        a.refresh_from_db()
        self.assertEqual((a.recruitment_id, a.link_url), (None, None))

    def test_soft_delete_hides_and_records_optional_reason(self):
        other_admin = make_user(is_admin=True)
        a = _create(self.admin)
        b = _create(self.admin)
        services.soft_delete_announcement(a, actor=self.admin)
        services.soft_delete_announcement(b, actor=other_admin, reason="内容过期")
        self.assertEqual(_ids(), [])
        self.assertIsNone(selectors.get_announcement(a.pk))
        self.assertTrue(Announcement.objects.filter(pk=a.pk).exists())
        logs = {
            log.target_id: log
            for log in AuditLog.objects.filter(action=actions.ANNOUNCEMENT_DELETE)
        }
        self.assertIsNone(logs[a.pk].reason)
        self.assertEqual((logs[b.pk].reason, logs[b.pk].actor_id), ("内容过期", other_admin.pk))

    def test_get_announcement(self):
        a = _create(self.admin)
        self.assertEqual(selectors.get_announcement(a.pk).pk, a.pk)
        self.assertIsNone(selectors.get_announcement(a.pk + 999))

    def test_recruitment_is_protected(self):
        recruitment = make_recruitment(make_user())
        _create(self.admin, recruitment=recruitment)
        with self.assertRaises(ProtectedError):
            recruitment.delete()
