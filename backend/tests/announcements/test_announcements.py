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
            (a.recruitment_id, a.link_url, a.is_pinned, a.submitted_by_id),
            (recruitment.pk, "https://example.com", False, None),
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
        # 保留字段 is_pinned 不参与排序
        Announcement.objects.filter(pk=first.pk).update(is_pinned=True)
        self.assertEqual(_ids(), [third.pk, second.pk, first.pk])
        Announcement.objects.filter(pk=first.pk).update(is_pinned=False)
        self.assertEqual(_ids(), [third.pk, second.pk, first.pk])

    def test_revoked_admin_cannot_delete_or_publish(self):
        revoked = make_user(is_admin=True)
        a = _create(revoked)
        User.objects.filter(pk=revoked.pk).update(is_admin=False)
        for call in (
            lambda: services.soft_delete_announcement(a.pk, actor=revoked),
            lambda: services.governance_delete_announcement(a.pk, actor=revoked, reason="r"),
            lambda: services.create_announcement(
                actor=revoked, title="t", content="c", time_kind="event", event_at=now()
            ),
        ):
            with self.subTest(), self.assertRaises(Forbidden):
                call()
        self.assertIsNotNone(selectors.get_announcement(a.pk))

    def test_self_soft_delete_notifies_publisher(self):
        a = _create(self.admin)
        services.soft_delete_announcement(a.pk, actor=self.admin)
        self.assertEqual(_ids(), [])
        self.assertIsNone(selectors.get_announcement(a.pk))
        self.assertTrue(Announcement.objects.filter(pk=a.pk).exists())
        log = AuditLog.objects.get(action=actions.ANNOUNCEMENT_DELETE)
        self.assertIsNone(log.reason)
        notice = Notification.objects.get(type=types.ANNOUNCEMENT_REMOVED)
        self.assertEqual((notice.recipient_id, notice.announcement_id), (self.admin.pk, a.pk))

    def test_deletion_notifies_publisher_and_submitter_dedup(self):
        """删除结果通知发布人与投稿人；两者相同只通知一次。"""
        submitter = make_user()
        both = make_user(is_admin=True)
        reviewed = _create(self.admin, submitted_by=submitter)
        services.governance_delete_announcement(reviewed.pk, actor=make_user(is_admin=True), reason="违规")
        self.assertEqual(
            set(Notification.objects.filter(announcement=reviewed).values_list("recipient_id", flat=True)),
            {self.admin.pk, submitter.pk},
        )
        self.assertEqual(Notification.objects.filter(type=types.ANNOUNCEMENT_ADMIN_REMOVED).count(), 2)

        # 发布人即投稿人：只通知一次
        own = _create(both, submitted_by=both)
        services.soft_delete_announcement(own.pk, actor=both)
        self.assertEqual(Notification.objects.filter(announcement=own).count(), 1)
        self.assertEqual(
            Notification.objects.get(announcement=own).type, types.ANNOUNCEMENT_REMOVED,
        )

    def test_governance_delete_with_reason_notifies_with_reason(self):
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
        self.assertEqual(Notification.objects.filter(announcement=a).count(), 1)

    def test_get_announcement(self):
        a = _create(self.admin)
        self.assertEqual(selectors.get_announcement(a.pk).pk, a.pk)
        self.assertIsNone(selectors.get_announcement(a.pk + 999))

    def test_recruitment_is_protected(self):
        recruitment = make_recruitment(make_user())
        _create(self.admin, recruitment=recruitment)
        with self.assertRaises(ProtectedError):
            recruitment.delete()
