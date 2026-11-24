"""投稿审核与删除结果通过正式收件箱接口可见、可标记。"""
from datetime import timedelta

from rest_framework.test import APIClient

from apps.announcements.models import Announcement
from apps.core import clock
from tests.base import TxTestCase
from tests.factories import make_user


class SubmissionMailboxTest(TxTestCase):
    url = "/api/v1/notifications"

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def check_deletion(self, governance):
        publisher = self.as_user(make_user(is_admin=True))
        submitter = self.as_user(make_user())
        unrelated = self.as_user(make_user())
        fields = {"title": "活动公告", "content": "活动详情", "time_kind": "event",
                  "event_at": (clock.now() + timedelta(days=2)).isoformat()}
        submission = submitter.post("/api/v1/announcement-submissions", fields, format="json").data["data"]["id"]
        actions = f"/api/v1/admin/announcement-submissions/{submission}"
        claim = publisher.post(actions + "/claim", {}, format="json").data["data"]
        approval = publisher.post(actions + "/approve", {"claim_id": claim["claim_id"]}, format="json")
        announcement = approval.data["data"]["announcement_id"]
        self.assertEqual(submitter.get(self.url + "/unread-count").data["data"]["unread_count"], 1)
        if governance:
            deletion = self.as_user(make_user(is_admin=True)).delete(
                f"/api/v1/admin/announcements/{announcement}", {"reason": "活动取消"}, format="json",
            )
        else:
            deletion = publisher.delete(f"/api/v1/announcements/{announcement}", {}, format="json")
        self.assertEqual(deletion.status_code, 200)
        inbox = submitter.get(self.url, {"is_read": "false"}).data["data"]
        self.assertEqual(inbox["total"], 2)
        self.assertEqual(publisher.get(self.url).data["data"]["total"], 1)
        self.assertEqual(unrelated.get(self.url).data["data"]["total"], 0)
        for notice in inbox["items"]:
            self.assertTrue(notice["target_is_deleted"])
        read = f"{self.url}/{inbox['items'][0]['id']}/read"
        self.assertEqual(unrelated.post(read, {}, format="json").status_code, 404)
        self.assertEqual(submitter.post(read, {}, format="json").status_code, 200)
        self.assertEqual(submitter.post(self.url + "/read-all", {}, format="json").data["data"]["updated_count"], 1)
        self.assertEqual(submitter.get(self.url + "/unread-count").data["data"]["unread_count"], 0)

    def test_owner_deletion_notifies_both_parties(self):
        self.check_deletion(False)

    def test_governance_deletion_notifies_both_parties(self):
        self.check_deletion(True)

    def test_same_publisher_and_submitter_receives_one_deletion(self):
        user = make_user(is_admin=True)
        announcement = Announcement.objects.create(
            author=user, submitted_by=user, title="活动公告", content="详情", time_kind="event", event_at=clock.now(),
        )
        client = self.as_user(user)
        self.assertEqual(client.delete(f"/api/v1/announcements/{announcement.pk}", {}, format="json").status_code, 200)
        inbox = client.get(self.url).data["data"]
        self.assertEqual(inbox["total"], 1)
        self.assertEqual(inbox["items"][0]["type"], "announcement_removed")
