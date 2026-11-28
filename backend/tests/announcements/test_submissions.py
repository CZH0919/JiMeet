"""公告投稿、审核与治理的接口及并发测试，用例对应 AT-09/AT-11 投稿审核部分。"""
from datetime import timedelta

from apps.announcements.models import Announcement, AnnouncementSubmission
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.core import clock
from apps.core.errors import ErrorCode
from apps.notifications import types
from apps.notifications.models import Notification
from tests.base import TxTestCase
from tests.factories import make_user

SUBMIT_URL = "/api/v1/announcement-submissions"
MINE_URL = "/api/v1/me/announcement-submissions"
ADMIN_URL = "/api/v1/admin/announcement-submissions"


def action_url(pk: int, action: str) -> str:
    return f"{ADMIN_URL}/{pk}/{action}"


def valid_payload(**overrides):
    payload = {
        "title": "投稿公告",
        "content": "报名方式：站内联系。",
        "time_kind": "event",
        "event_at": (clock.now() + timedelta(days=3)).isoformat(),
        "link_url": "https://example.com/apply",
    }
    payload.update(overrides)
    return payload


class SubmissionAPITest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user(is_admin=True)
        self.other_admin = make_user(is_admin=True)
        self.user = make_user()
        self.client.force_authenticate(user=self.user)

    def submit(self, **overrides):
        return self.client.post(SUBMIT_URL, valid_payload(**overrides), format="json")

    def claim(self, pk):
        response = self.client.post(action_url(pk, "claim"), {}, format="json")
        self.assertEqual(response.status_code, 200)
        return response.data["data"]

    def test_submit_and_view_own_submissions(self):
        """第 5 条可提交；本人可查看状态与驳回理由，他人不可见。"""
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertEqual(data["status"], "pending")
        self.assertIsNone(data["reject_reason"])
        self.assertIsNone(data["announcement_id"])

        mine = self.client.get(MINE_URL)
        self.assertEqual(mine.status_code, 200)
        self.assertEqual((mine.data["data"]["total"], mine.data["data"]["items"][0]["title"]),
                         (1, "投稿公告"))
        self.client.force_authenticate(user=make_user())
        other_view = self.client.get(MINE_URL)
        self.assertEqual(other_view.data["data"]["total"], 0)

    def test_daily_and_pending_limits_include_current(self):
        """第 6 条在相应限额下被拒：上海自然日 5 条、同时待审 5 条，均含本次。"""
        for index in range(5):
            self.assertEqual(self.submit(title=f"第{index}条").status_code, 201)
        limited = self.submit(title="第6条")
        self.assertEqual(limited.status_code, 409)
        self.assertEqual(limited.data["code"], ErrorCode.SUBMISSION_LIMIT_EXCEEDED)

        # 驳回 3 条后当日额度仍占用，但待审额度释放
        self.client.force_authenticate(user=self.admin)
        pending = [row.pk for row in AnnouncementSubmission.objects.filter(status="pending")][:3]
        for pk in pending:
            batch = self.claim(pk)["claim_id"]
            response = self.client.post(action_url(pk, "reject"), {"claim_id": batch, "reason": "不合规"}, format="json")
            self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(user=self.user)
        still_limited = self.submit(title="驳回后同日再投")
        self.assertEqual(still_limited.status_code, 409)

    def test_pending_limit_releases_when_queue_drains(self):
        for index in range(5):
            self.assertEqual(self.submit(title=f"待审{index}").status_code, 201)
        self.client.force_authenticate(user=self.admin)
        first = AnnouncementSubmission.objects.order_by("id").first()
        batch = self.claim(first.pk)["claim_id"]
        self.assertEqual(self.client.post(action_url(first.pk, "approve"), {"claim_id": batch}, format="json").status_code, 200)
        self.client.force_authenticate(user=self.user)
        # 次日提交避开每日额度，验证待审额度已随通过释放
        with self.freeze_at(clock.now() + timedelta(days=1)):
            response = self.submit(title="通过后补投")
        self.assertEqual(response.status_code, 201)

    def test_admin_queue_ordering_overdue_first_and_total(self):
        """超 24 小时未处理优先并带逾期标记，组内按提交时间、编号升序。"""
        self.assertEqual(self.submit(title="老稿").status_code, 201)
        old = AnnouncementSubmission.objects.get()
        AnnouncementSubmission.objects.filter(pk=old.pk).update(
            submitted_at=clock.now() - timedelta(hours=25),
        )
        self.assertEqual(self.submit(title="新稿").status_code, 201)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(ADMIN_URL)
        items = response.data["data"]["items"]
        self.assertEqual(response.data["data"]["total"], 2)
        self.assertEqual([item["title"] for item in items], ["老稿", "新稿"])
        self.assertEqual([item["overdue"] for item in items], [True, False])
        self.assertEqual(set(items[0]), {"id", "title", "content", "time_kind", "event_at", "link_url",
                                         "submitted_at", "submitter", "claimed_by", "claimed_until", "overdue"})
        mine_fields = {"id", "title", "content", "time_kind", "event_at", "link_url", "submitted_at",
                       "status", "reviewed_at", "reject_reason", "announcement_id"}
        claimed = self.claim(old.pk)
        self.assertEqual(set(claimed), mine_fields | {"claim_id", "claimed_until"})
        released = self.client.post(action_url(old.pk, "release"), {"claim_id": claimed["claim_id"]}, format="json")
        self.assertEqual(set(released.data["data"]), mine_fields)

    def test_claim_competition_only_one_admin(self):
        """两名管理员竞争同一稿件仅一人可处理。"""
        self.submit()
        submission = AnnouncementSubmission.objects.get()
        self.client.force_authenticate(user=self.admin)
        batch = self.claim(submission.pk)["claim_id"]
        self.client.force_authenticate(user=self.other_admin)
        blocked = self.client.post(action_url(submission.pk, "claim"), {}, format="json")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data["code"], ErrorCode.SUBMISSION_LOCKED)
        denied = self.client.post(action_url(submission.pk, "approve"), {"claim_id": batch}, format="json")
        self.assertEqual(denied.status_code, 409)

    def test_release_and_expiry_allow_takeover_and_block_old_claimant(self):
        """交回或到期后原领取人不能再凭旧领取记录处理。"""
        self.submit()
        submission = AnnouncementSubmission.objects.get()
        self.client.force_authenticate(user=self.admin)
        batch = self.claim(submission.pk)["claim_id"]
        self.assertEqual(self.client.post(action_url(submission.pk, "release"), {"claim_id": batch}, format="json").status_code, 200)
        stale = self.client.post(action_url(submission.pk, "approve"), {"claim_id": batch}, format="json")
        self.assertEqual(stale.status_code, 409)

        self.client.force_authenticate(user=self.other_admin)
        self.assertEqual(self.client.post(action_url(submission.pk, "claim"), {}, format="json").status_code, 200)
        # 15 分钟后领取到期，第三位管理员可接手
        with self.freeze_at(clock.now() + timedelta(minutes=16)):
            third = make_user(is_admin=True)
            self.client.force_authenticate(user=third)
            self.assertEqual(self.client.post(action_url(submission.pk, "claim"), {}, format="json").status_code, 200)

    def test_approve_creates_announcement_with_publisher_and_submitter(self):
        """通过时按投稿原文生成公告，发布人记审核管理员，投稿人另记；结果、审计、通知同事务。"""
        self.submit(title="过审稿")
        submission = AnnouncementSubmission.objects.get()
        self.client.force_authenticate(user=self.admin)
        batch = self.claim(submission.pk)["claim_id"]
        response = self.client.post(action_url(submission.pk, "approve"), {"claim_id": batch}, format="json")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["status"], "approved")
        self.assertIsNotNone(data["announcement_id"])

        announcement = Announcement.objects.get(pk=data["announcement_id"])
        self.assertEqual((announcement.title, announcement.author_id, announcement.submitted_by_id),
                         ("过审稿", self.admin.pk, self.user.pk))
        self.assertTrue(AuditLog.objects.filter(
            action=actions.ANNOUNCEMENT_SUBMISSION_APPROVE, target_id=submission.pk,
        ).exists())
        notice = Notification.objects.get(type=types.ANNOUNCEMENT_SUBMISSION_APPROVED)
        self.assertEqual((notice.recipient_id, notice.announcement_id),
                         (self.user.pk, announcement.pk))
        # 每次成功审核只产生一次业务结果
        again = self.client.post(action_url(submission.pk, "approve"), {"claim_id": batch}, format="json")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data["code"], ErrorCode.SUBMISSION_ALREADY_PROCESSED)
        self.assertEqual(Announcement.objects.count(), 1)

    def test_reject_requires_reason_and_notifies_submitter(self):
        self.submit(title="拒稿")
        submission = AnnouncementSubmission.objects.get()
        self.client.force_authenticate(user=self.admin)
        batch = self.claim(submission.pk)["claim_id"]
        self.assertEqual(
            self.client.post(action_url(submission.pk, "reject"), {"claim_id": batch}, format="json").status_code, 400,
        )
        response = self.client.post(
            action_url(submission.pk, "reject"), {"reason": "非竞赛活动信息", "claim_id": batch}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual((submission.status, submission.reject_reason), ("rejected", "非竞赛活动信息"))
        notice = Notification.objects.get(type=types.ANNOUNCEMENT_SUBMISSION_REJECTED)
        self.assertEqual(notice.recipient_id, self.user.pk)
        self.assertIn("非竞赛活动信息", notice.content)
        self.assertIn("拒稿", notice.content)
        self.assertIsNone(notice.announcement_id)
        self.assertTrue(AuditLog.objects.filter(
            action=actions.ANNOUNCEMENT_SUBMISSION_REJECT, target_id=submission.pk,
        ).exists())
        # 重复处理只产生一次业务结果
        again = self.client.post(
            action_url(submission.pk, "reject"), {"reason": "再次驳回", "claim_id": batch}, format="json",
        )
        self.assertEqual(again.status_code, 409)

    def test_active_claim_retries_and_stale_actions(self):
        pk = self.submit().data["data"]["id"]
        self.client.force_authenticate(user=self.admin)
        start = clock.now()
        with self.freeze_at(start):
            first = self.claim(pk)
        with self.freeze_at(start + timedelta(minutes=10)):
            repeated = self.claim(pk)
            self.assertEqual((first["claim_id"], first["claimed_until"]),
                             (repeated["claim_id"], repeated["claimed_until"]))
        with self.freeze_at(start + timedelta(minutes=15)):
            old = {"claim_id": first["claim_id"]}
            self.assertEqual(self.client.post(action_url(pk, "approve"), old, format="json").status_code, 409)
            current = self.claim(pk)
            self.assertNotEqual(current["claim_id"], first["claim_id"])
            for action in ("approve", "release", "reject"):
                body = dict(old, reason="内容不完整") if action == "reject" else old
                self.assertEqual(self.client.post(action_url(pk, action), body, format="json").status_code, 409)
            for body in ({}, {"claim_id": "invalid"}, {"claim_id": 1}, {"claim_id": True}):
                self.assertEqual(self.client.post(action_url(pk, "approve"), body, format="json").status_code, 400)
            confirmed = self.client.post(action_url(pk, "approve"), {"claim_id": current["claim_id"]}, format="json")
            self.assertEqual(confirmed.status_code, 200)
            self.assertEqual(Announcement.objects.count(), 1)

    def test_legacy_claim_keeps_expiry_and_release_rotates_batch(self):
        pk = self.submit().data["data"]["id"]
        until = clock.now() + timedelta(minutes=6)
        AnnouncementSubmission.objects.filter(pk=pk).update(claimed_by=self.admin, claimed_until=until)
        self.client.force_authenticate(user=self.admin)
        batch = self.claim(pk)["claim_id"]
        self.assertEqual(AnnouncementSubmission.objects.get(pk=pk).claimed_until, until)
        self.assertEqual(self.client.post(action_url(pk, "release"), {"claim_id": batch}, format="json").status_code, 200)
        self.assertNotEqual(self.claim(pk)["claim_id"], batch)
        self.assertEqual(self.client.post(action_url(pk, "approve"), {"claim_id": batch}, format="json").status_code, 409)

    def test_promoted_submitter_keeps_history_and_publishes_directly(self):
        self.assertEqual(self.submit().status_code, 201)
        type(self.user).objects.filter(pk=self.user.pk).update(is_admin=True)
        denied = self.submit()
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(AnnouncementSubmission.objects.count(), 1)
        self.user.refresh_from_db()
        self.assertEqual(self.client.get(MINE_URL).data["data"]["total"], 1)
        self.assertEqual(self.client.post("/api/v1/announcements", valid_payload(), format="json").status_code, 201)

    def test_submission_has_no_edit_or_withdraw_entry(self):
        """提交后不能改稿、撤回：无编辑/撤回入口。"""
        self.submit()
        submission = AnnouncementSubmission.objects.get()
        self.assertEqual(self.client.patch(f"{SUBMIT_URL}/{submission.pk}", {}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(f"{SUBMIT_URL}/{submission.pk}", {}, format="json").status_code, 404)
        self.assertEqual(self.client.patch(SUBMIT_URL, {}, format="json").status_code, 405)
        self.assertEqual(AnnouncementSubmission.objects.get(pk=submission.pk).status, "pending")

    def test_admin_entries_require_admin(self):
        """普通用户不能查看待审池或执行审核动作。"""
        self.submit()
        submission = AnnouncementSubmission.objects.get()
        self.assertEqual(self.client.get(ADMIN_URL).status_code, 403)
        for action_name in ("claim", "release", "approve", "reject"):
            response = self.client.post(
                action_url(submission.pk, action_name), {"reason": "r"}, format="json",
            )
            self.assertEqual(response.status_code, 403)

    def test_claim_requires_pending_status(self):
        self.submit()
        submission = AnnouncementSubmission.objects.get()
        self.client.force_authenticate(user=self.admin)
        batch = self.claim(submission.pk)["claim_id"]
        self.client.post(action_url(submission.pk, "approve"), {"claim_id": batch}, format="json")
        response = self.client.post(action_url(submission.pk, "claim"), {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], ErrorCode.SUBMISSION_ALREADY_PROCESSED)
