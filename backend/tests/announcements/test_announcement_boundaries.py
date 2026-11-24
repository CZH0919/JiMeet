"""公告链接校验及治理操作的并发、事务回归。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import mock

from django.db import close_old_connections, connections

from apps.announcements import services
from apps.announcements.models import Announcement
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.core import clock
from apps.core.errors import BizError
from apps.notifications.models import Notification
from tests.base import TxTestCase
from tests.factories import make_user


class AnnouncementBoundaryTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.actor = make_user(is_admin=True)
        self.login(self.actor)
        self.payload = {
            "title": "活动公告", "content": "报名说明", "time_kind": "event",
            "event_at": (clock.now() + timedelta(days=2)).isoformat(),
        }

    def _create(self):
        return services.create_announcement(actor=self.actor, **dict(
            self.payload, event_at=clock.now() + timedelta(days=2),
        ))

    def _parallel(self, jobs):
        gate = Barrier(len(jobs))

        def run(job):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                return job()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return [future.result(timeout=20) for future in futures]

    def test_invalid_links_return_400_without_side_effects(self):
        announcement = self._create()
        before = AuditLog.objects.count()
        for link in (
            "https://[", "https://[invalid]", "https://example.com:65536",
            "https://example.com:not-a-port", "https://exa mple.com", "http:///missing",
            "ftp://example.com", "/relative",
        ):
            with self.subTest(link=link):
                response = self.client.post("/api/v1/announcements", dict(self.payload, link_url=link), format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], "VALIDATION_ERROR")
                self.assertEqual(Announcement.objects.count(), 1)
                self.assertEqual(AuditLog.objects.count(), before)
                self.assertFalse(Notification.objects.exists())
        # 编辑入口已收回
        self.assertEqual(
            self.client.patch(f"/api/v1/announcements/{announcement.pk}", {"link_url": "https://example.com"}, format="json").status_code,
            405,
        )
        announcement.refresh_from_db()
        self.assertIsNone(announcement.link_url)

    def test_valid_links_and_null_remain_usable(self):
        for link in (None, "https://example.com/apply?q=1", "http://localhost:8080/", "https://[::1]:8443/"):
            with self.subTest(link=link):
                response = self.client.post("/api/v1/announcements", dict(self.payload, link_url=link), format="json")
                self.assertEqual(response.status_code, 201)

    def test_concurrent_governance_deletion_produces_one_notice(self):
        announcement = self._create()

        def remove():
            try:
                services.governance_delete_announcement(announcement.pk, actor=self.actor, reason="处置原因")
                return 200
            except BizError as error:
                return error.http_status

        self.assertEqual(sorted(self._parallel([remove, remove])), [200, 404])
        self.assertEqual(Notification.objects.filter(announcement=announcement).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action=actions.ANNOUNCEMENT_DELETE).count(), 1)

    def test_concurrent_claim_allows_only_one_admin(self):
        """两名管理员并发领取同一投稿，仅一人成功。"""
        from apps.announcements.models import AnnouncementSubmission

        submitter = make_user()
        submission = services.create_submission(
            submitter=submitter, title="竞争稿", content="正文",
            time_kind="event", event_at=clock.now() + timedelta(days=2),
        )
        other_admin = make_user(is_admin=True)

        def claim(actor):
            try:
                services.claim_submission(submission.pk, actor=actor)
                return 200
            except BizError as error:
                return error.http_status

        outcomes = self._parallel([
            lambda: claim(self.actor),
            lambda: claim(other_admin),
        ])
        self.assertEqual(sorted(outcomes), [200, 409])
        submission.refresh_from_db()
        self.assertIn(submission.claimed_by_id, (self.actor.pk, other_admin.pk))

    def test_notification_failure_rolls_back_governance(self):
        announcement = self._create()
        with mock.patch.object(services, "notify", side_effect=RuntimeError("notification unavailable")):
            with self.assertRaises(RuntimeError):
                services.governance_delete_announcement(announcement.pk, actor=self.actor, reason="处置原因")
        announcement.refresh_from_db()
        self.assertIsNone(announcement.deleted_at)
        self.assertFalse(AuditLog.objects.filter(action=actions.ANNOUNCEMENT_DELETE).exists())
