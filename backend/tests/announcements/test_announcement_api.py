"""公告 HTTP 层测试，用例对应 AT-09/AT-02/AT-11。"""
from datetime import timedelta

from apps.accounts.models import User
from apps.announcements.models import Announcement
from apps.audit.models import AuditLog
from apps.core import clock
from apps.notifications import types
from apps.notifications.models import EmailLog, Notification
from tests.base import TxTestCase
from tests.factories import make_recruitment, make_user

LIST_URL = "/api/v1/announcements"


def detail_url(pk: int) -> str:
    return f"{LIST_URL}/{pk}"


def govern_url(pk: int) -> str:
    return f"/api/v1/admin/announcements/{pk}"


def valid_payload(**overrides):
    payload = {
        "title": "竞赛公告",
        "content": "报名方式：站内申请。",
        "time_kind": "event",
        "event_at": (clock.now() + timedelta(days=3)).isoformat(),
    }
    payload.update(overrides)
    return payload


class AnnouncementAPITest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user(is_admin=True)
        self.other_admin = make_user(is_admin=True)
        self.user = make_user()

    def test_list_requires_login_and_sorts_by_created_at_desc(self):
        """AT-09-01/02：未登录 401；列表稳定倒序，置顶不影响排序。"""
        from rest_framework.test import APIClient

        self.assertEqual(APIClient().get(LIST_URL).status_code, 401)

        self.client.force_authenticate(user=self.admin)
        first = self.client.post(LIST_URL, valid_payload(title="first"), format="json")
        second = self.client.post(LIST_URL, valid_payload(title="second"), format="json")
        third = self.client.post(LIST_URL, valid_payload(title="third"), format="json")
        self.assertEqual(
            (first.status_code, second.status_code, third.status_code), (201, 201, 201)
        )
        # 既有置顶数据不改变列表顺序。
        Announcement.objects.filter(pk=first.data["data"]["id"]).update(is_pinned=True)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.data["data"]["items"]]
        self.assertEqual(titles, ["third", "second", "first"])
        self.assertEqual(response.data["data"]["total"], 3)

    def test_create_validation_errors(self):
        """AT-09-03：缺字段、非法枚举、非法链接、非法关联招募均 400。"""
        self.client.force_authenticate(user=self.admin)
        cases = (
            ({"title": "仅标题"}, "缺必填字段"),
            (valid_payload(title=""), "空标题"),
            (valid_payload(time_kind="bad"), "非法时间类型"),
            (valid_payload(event_at="2026-11-15T18:00:00"), "无时区时间"),
            (valid_payload(link_url="ftp://example.com"), "非法协议"),
            (valid_payload(link_url="/relative/path"), "相对路径"),
            (valid_payload(link_url="https://" + "x" * 500), "超长链接"),
            (valid_payload(recruitment_id=999999), "不存在的招募"),
            (valid_payload(is_pinned=True), "置顶不可写"),
            (valid_payload(unknown=1), "未知字段"),
        )
        for payload, label in cases:
            with self.subTest(case=label):
                response = self.client.post(LIST_URL, payload, format="json")
                self.assertEqual(response.status_code, 400, label)
        self.assertEqual(Announcement.objects.count(), 0)

    def test_create_accepts_past_event_and_valid_recruitment(self):
        """AT-09-04：过去时间公告允许创建；合法关联招募与链接可用。"""
        recruitment = make_recruitment(make_user())
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(LIST_URL, valid_payload(
            event_at=(clock.now() - timedelta(days=1)).isoformat(),
            link_url="https://example.com/form",
            recruitment_id=recruitment.pk,
        ), format="json")
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertTrue(data["recruitment_available"])
        self.assertEqual(data["recruitment_id"], recruitment.pk)
        self.assertEqual(data["author"]["uid"], self.admin.uid)
        self.assertEqual(
            data["permissions"],
            {"can_edit": True, "can_delete": True, "can_govern_delete": True},
        )

    def test_recruitment_availability_follows_recruitment_deletion(self):
        recruitment = make_recruitment(make_user())
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(recruitment_id=recruitment.pk),
                             format="json").data["data"]["id"]
        recruitment.deleted_at = clock.now()
        recruitment.save(update_fields=["deleted_at"])
        data = self.client.get(detail_url(pk)).data["data"]
        self.assertFalse(data["recruitment_available"])

    def test_write_requires_admin(self):
        """AT-09-05：普通用户创建/编辑/删除均 403。"""
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(), format="json").data["data"]["id"]
        self.client.force_authenticate(user=self.user)
        for response in (
            self.client.post(LIST_URL, valid_payload(), format="json"),
            self.client.patch(detail_url(pk), {"title": "x"}, format="json"),
            self.client.delete(detail_url(pk), {}, format="json"),
            self.client.delete(govern_url(pk), {"reason": "r"}, format="json"),
        ):
            self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(Announcement.objects.filter(pk=pk, deleted_at__isnull=True).first())

    def test_patch_requires_author_and_updates_partially(self):
        """AT-09-06/07：其他管理员不能编辑；作者部分更新成功。"""
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(), format="json").data["data"]["id"]

        self.client.force_authenticate(user=self.other_admin)
        self.assertEqual(
            self.client.patch(detail_url(pk), {"title": "越权"}, format="json").status_code, 403
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(detail_url(pk), {"title": "改标题"}, format="json")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual((data["title"], data["content"]), ("改标题", "报名方式：站内申请。"))
        self.assertEqual(
            self.client.patch(detail_url(pk), {}, format="json").status_code, 400
        )
        self.assertEqual(
            self.client.patch(detail_url(pk), {"is_pinned": True}, format="json").status_code, 400
        )

    def test_self_delete_without_notification(self):
        """AT-09-08：本人删除软删、无通知、无原因审计。"""
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(), format="json").data["data"]["id"]
        response = self.client.delete(detail_url(pk), {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(detail_url(pk)).status_code, 404)
        self.assertTrue(Announcement.objects.filter(pk=pk).exists())
        self.assertIsNone(AuditLog.objects.get(action="announcement_delete").reason)
        self.assertEqual(Notification.objects.count(), 0)

    def test_governance_delete_with_reason_notifies_author(self):
        """AT-09-09/10/15、AT-11-02/04：治理删除原因必填，同事务通知作者。"""
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(title="违规公告"), format="json").data["data"]["id"]

        self.client.force_authenticate(user=self.other_admin)
        self.assertEqual(
            self.client.delete(govern_url(pk), {"reason": " "}, format="json").status_code, 400
        )
        self.assertEqual(
            self.client.delete(govern_url(pk), {}, format="json").status_code, 400
        )
        response = self.client.delete(govern_url(pk), {"reason": "内容违规"}, format="json")
        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.get(action="announcement_delete")
        self.assertEqual((log.reason, log.actor_id), ("内容违规", self.other_admin.pk))
        notice = Notification.objects.get(type=types.ANNOUNCEMENT_ADMIN_REMOVED)
        self.assertEqual((notice.recipient_id, notice.announcement_id), (self.admin.pk, pk))
        self.assertIn("违规公告", notice.content)
        self.assertIn("内容违规", notice.content)
        self.assertEqual(EmailLog.objects.count(), 0)

    def test_repeated_delete_returns_404_without_duplicate_side_effects(self):
        """AT-09-11：重复删除 404，不重复审计与通知。"""
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(), format="json").data["data"]["id"]
        self.assertEqual(self.client.delete(detail_url(pk), {}, format="json").status_code, 200)
        for response in (
            self.client.delete(detail_url(pk), {}, format="json"),
            self.client.delete(govern_url(pk), {"reason": "重复"}, format="json"),
        ):
            self.assertEqual(response.status_code, 404)
        self.assertEqual(AuditLog.objects.filter(action="announcement_delete").count(), 1)
        self.assertEqual(Notification.objects.count(), 0)

    def test_update_after_delete_race_cannot_resurrect(self):
        """AT-09-12：删除后更新按 404 处理，公告不会复活。"""
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(title="原标题"), format="json").data["data"]["id"]
        self.assertEqual(self.client.delete(detail_url(pk), {}, format="json").status_code, 200)
        self.assertEqual(
            self.client.patch(detail_url(pk), {"title": "复活"}, format="json").status_code, 404
        )
        self.assertEqual(Announcement.objects.get(pk=pk).title, "原标题")

    def test_revoked_admin_rejected_on_all_entries(self):
        """AT-09-13、AT-02-02：撤权后旧会话的全部公告写操作被拒。"""
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(), format="json").data["data"]["id"]
        User.objects.filter(pk=self.admin.pk).update(is_admin=False)
        self.admin.refresh_from_db()
        for response in (
            self.client.post(LIST_URL, valid_payload(), format="json"),
            self.client.patch(detail_url(pk), {"title": "x"}, format="json"),
            self.client.delete(detail_url(pk), {}, format="json"),
            self.client.delete(govern_url(pk), {"reason": "r"}, format="json"),
        ):
            self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(Announcement.objects.filter(pk=pk, deleted_at__isnull=True).first())

    def test_collection_rejects_wrong_methods(self):
        """AT-09-14：集合路径 PATCH/DELETE 为 405。"""
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.patch(LIST_URL, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(LIST_URL, {}, format="json").status_code, 405)

    def test_governance_notification_in_list_with_announcement_id(self):
        self.client.force_authenticate(user=self.admin)
        pk = self.client.post(LIST_URL, valid_payload(), format="json").data["data"]["id"]
        self.client.force_authenticate(user=self.other_admin)
        self.client.delete(govern_url(pk), {"reason": "违规"}, format="json")
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/v1/notifications")
        self.assertEqual(response.status_code, 200)
        item = response.data["data"]["items"][0]
        self.assertEqual(
            (item["type"], item["announcement_id"], item["recruitment_id"]),
            (types.ANNOUNCEMENT_ADMIN_REMOVED, pk, None),
        )
