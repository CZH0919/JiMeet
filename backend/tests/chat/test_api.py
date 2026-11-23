"""对方主页、参与者私有会话及显式已读回执的接口回归。"""
from datetime import timedelta

from rest_framework.test import APIClient

from apps.chat.models import ChatConversation, ChatMessage
from apps.core import clock
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


BASE = "/api/v1/chat/conversations"
PROFILE = "/api/v1/users/"


class ChatApiTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.member = make_user()
        self.owner = make_user(role="teacher")
        self.job = make_recruitment(self.owner)
        self.client.force_authenticate(user=self.member)

    def open(self, **changes):
        fields = {"peer_uid": self.owner.uid, "recruitment_id": self.job.pk}
        return self.client.post(BASE, dict(fields, **changes), format="json")

    def test_profile_and_creation_from_public_recruitment(self):
        profile = self.client.get(PROFILE + self.owner.uid, {"recruitment_id": self.job.pk})
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["data"], {"uid": self.owner.uid, "nickname": self.owner.nickname,
                         "role": "teacher", "chat": {"can_chat": True, "conversation_id": None}})
        self.assertFalse(ChatConversation.objects.exists())
        created = self.open()
        self.assertEqual(created.status_code, 201)
        data = created.data["data"]
        self.assertEqual(set(data), {"id", "peer", "last_message", "updated_at", "unread_count"})
        self.assertEqual((data["last_message"], data["unread_count"]), (None, 0))
        self.assertEqual(data["peer"], {k: profile.data["data"][k] for k in ("uid", "nickname", "role")})
        self.job.deleted_at = clock.now()
        self.job.save(update_fields=["deleted_at"])
        self.client.force_authenticate(user=self.owner)
        existing = self.client.post(BASE, {"peer_uid": self.member.uid}, format="json")
        self.assertEqual((existing.status_code, existing.data["data"]["id"]), (200, data["id"]))
        self.assertEqual(self.client.get(PROFILE + self.member.uid).data["data"]["chat"]["conversation_id"], data["id"])
        self.assertEqual(ChatConversation.objects.count(), 1)

    def test_application_entry_is_only_for_its_publisher(self):
        app = make_application(self.job, self.member, status="withdrawn")
        staff = make_user(is_admin=True)
        self.client.force_authenticate(user=staff)
        for request in (self.client.get(PROFILE + self.member.uid, {"application_id": app.pk}),
                        self.client.post(BASE, {"peer_uid": self.member.uid, "application_id": app.pk}, format="json")):
            self.assertEqual(request.status_code, 404)
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.get(PROFILE + staff.uid, {"application_id": app.pk}).status_code, 404)
        self.job.deleted_at = clock.now()
        self.job.save(update_fields=["deleted_at"])
        # 发布者仍能查看保留的本人招聘申请历史，聊天入口独立于简历权限。
        self.assertEqual(self.client.get(PROFILE + self.member.uid, {"application_id": app.pk}).status_code, 200)
        self.assertEqual(self.client.post(BASE, {"peer_uid": self.member.uid, "application_id": app.pk},
                                          format="json").status_code, 201)

    def test_missing_wrong_and_deleted_sources_and_self(self):
        unrelated = make_user()
        for uid, source in ((self.owner.uid, {}), (unrelated.uid, {"recruitment_id": self.job.pk}),
                            ("0" * 32, {"recruitment_id": self.job.pk})):
            self.assertEqual(self.client.get(PROFILE + uid, source).status_code, 404)
            self.assertEqual(self.client.post(BASE, {"peer_uid": uid, **source}, format="json").status_code, 404)
        self.assertEqual(self.open(peer_uid=self.member.uid).status_code, 400)
        self.assertEqual(self.open(application_id=1).status_code, 400)
        self.assertEqual(self.client.get(PROFILE + self.owner.uid + "?recruitment_id=1&recruitment_id=2").status_code, 400)
        self.assertEqual(self.open(recruitment_id=True).status_code, 400)
        self.assertEqual(self.open(recruitment_id=str(self.job.pk)).status_code, 400)
        self.job.deleted_at = clock.now()
        self.job.save(update_fields=["deleted_at"])
        self.assertEqual(self.open().status_code, 404)
        self.assertFalse(ChatConversation.objects.exists())

    def test_unauthenticated_and_session_csrf(self):
        fresh = APIClient(enforce_csrf_checks=True)
        self.assertEqual(fresh.get(BASE).status_code, 401)
        fresh.force_login(self.member)
        fields = {"peer_uid": self.owner.uid, "recruitment_id": self.job.pk}
        denied = fresh.post(BASE, fields, format="json")
        self.assertEqual((denied.status_code, denied["Cache-Control"]), (403, "private, no-store"))
        token = fresh.get("/api/v1/auth/csrf").data["data"]["csrf_token"]
        allowed = fresh.post(BASE, fields, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual((allowed.status_code, allowed["Cache-Control"]), (201, "private, no-store"))

    def test_content_privacy_length_and_plaintext(self):
        cid = self.open().data["data"]["id"]
        url = f"{BASE}/{cid}/messages"
        content = "明天见 👩‍💻\n1 < 2"
        with self.assertLogs("apps.chat.services", "INFO") as logs:
            response = self.client.post(url, {"content": content}, format="json")
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertEqual(set(data), {"id", "conversation_id", "sender_uid", "recipient_uid", "content", "created_at", "read_at"})
        self.assertEqual((data["content"], data["sender_uid"], data["recipient_uid"], data["read_at"]),
                         (content, self.member.uid, self.owner.uid, None))
        self.assertNotIn(content.splitlines()[0], str(logs.output))
        self.assertEqual(self.client.post(url, {"content": "🙂" * 500}, format="json").status_code, 201)
        for body in ({"content": "🙂" * 501}, {"content": " \n\t"}, {"content": "<b>粗体</b>"},
                     {"content": 17}, {"content": ["图"]}, {"content": "a\x00b"}, {"content": "\u200b"},
                     {"content": "测试", "sender_uid": self.owner.uid}, {"file": "附件"}):
            self.assertEqual(self.client.post(url, body, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"content": "文本"}, format="multipart").status_code, 415)
        self.assertEqual(ChatMessage.objects.count(), 2)

    def test_offline_counts_receipts_and_third_party_isolation(self):
        cid = self.open().data["data"]["id"]
        url = f"{BASE}/{cid}/messages"
        read = f"{BASE}/{cid}/read"
        ids = [self.client.post(url, {"content": text}, format="json").data["data"]["id"]
               for text in ("第一条", "第二条", "第三条")]
        self.assertEqual(self.client.get(BASE + "/unread-count").data["data"]["unread_count"], 0)
        self.client.force_authenticate(user=self.owner)
        conversation = self.client.get(BASE).data["data"]["items"][0]
        self.assertEqual((conversation["unread_count"], conversation["last_message"]["id"]), (3, ids[-1]))
        self.assertEqual(self.client.get(url).data["data"]["total"], 3)
        self.assertEqual(self.client.get(BASE + "/unread-count").data["data"]["unread_count"], 3)
        own = self.client.post(url, {"content": "已收到"}, format="json").data["data"]["id"]
        for bad, code in (([ids[0], own], 404), ([ids[0], ids[0]], 400), ([], 400), ([True], 400)):
            self.assertEqual(self.client.post(read, {"message_ids": bad}, format="json").status_code, code)
        for count in (1, 0):
            result = self.client.post(read, {"message_ids": [ids[1]]}, format="json")
            self.assertEqual(result.data["data"]["updated_count"], count)
        self.assertEqual(self.client.get(BASE + "/unread-count").data["data"]["unread_count"], 2)
        self.assertEqual(self.client.get("/api/v1/notifications/unread-count").data["data"]["unread_count"], 0)
        self.assertEqual(list(ChatMessage.objects.filter(pk__in=ids, read_at__isnull=False).values_list("pk", flat=True)), [ids[1]])
        for third in (make_user(), make_user(is_admin=True)):
            self.client.force_authenticate(user=third)
            self.assertEqual(self.client.get(BASE).data["data"]["total"], 0)
            self.assertEqual(self.client.get(BASE + "/unread-count").data["data"]["unread_count"], 0)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {"content": "你好"}, format="json").status_code, 404)
            self.assertEqual(self.client.post(read, {"message_ids": [ids[0]]}, format="json").status_code, 404)
        self.assertEqual(ChatMessage.objects.count(), 4)

    def test_history_pagination_is_stable_with_new_messages(self):
        cid = self.open().data["data"]["id"]
        url = f"{BASE}/{cid}/messages"
        with self.freeze_at(clock.now()):
            ids = [self.client.post(url, {"content": str(i)}, format="json").data["data"]["id"] for i in range(5)]
            first = self.client.get(url, {"page_size": 2}).data["data"]["items"]
            self.assertEqual([i["id"] for i in first], ids[::-1][:2])
            self.client.post(url, {"content": "新消息"}, format="json")
            older = self.client.get(url, {"before_id": first[-1]["id"], "page_size": 2}).data["data"]
            self.assertEqual([item["id"] for item in older["items"]], [ids[2], ids[1]])
            self.assertEqual((older["total"], older["page"]), (3, 1))
        other_job = make_recruitment(make_user())
        cid2 = self.open(peer_uid=other_job.publisher.uid, recruitment_id=other_job.pk).data["data"]["id"]
        self.assertEqual(self.client.get(f"{BASE}/{cid2}/messages", {"before_id": ids[0]}).status_code, 404)
        self.assertEqual(self.client.get(url, {"page_size": 51}).status_code, 400)
        self.assertEqual(self.client.get(url, {"before_id": 0}).status_code, 400)

    def test_unread_total_and_batch_scope_across_conversations(self):
        first = self.open().data["data"]["id"]
        other = make_user()
        second = self.open(peer_uid=other.uid, recruitment_id=make_recruitment(other).pk).data["data"]["id"]
        mids = []
        for sender, cid in ((self.owner, first), (other, second)):
            self.client.force_authenticate(user=sender)
            msg = self.client.post(f"{BASE}/{cid}/messages", {"content": "周末见"}, format="json")
            mids.append(msg.data["data"]["id"])
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.client.get(BASE + "/unread-count").data["data"]["unread_count"], 2)
        wrong = self.client.post(f"{BASE}/{first}/read", {"message_ids": mids}, format="json")
        self.assertEqual(wrong.status_code, 404)
        self.assertEqual(self.client.get(BASE + "/unread-count").data["data"]["unread_count"], 2)
        self.client.post(f"{BASE}/{second}/read", {"message_ids": [mids[1]]}, format="json")
        summaries = self.client.get(BASE).data["data"]["items"]
        self.assertEqual(sum(c["unread_count"] for c in summaries), 1)
        self.assertEqual(self.client.get(BASE + "/unread-count").data["data"]["unread_count"], 1)

    def test_conversation_sort_and_peer_availability(self):
        one = self.open().data["data"]["id"]
        other = make_user()
        second_job = make_recruitment(other)
        two = self.open(peer_uid=other.uid, recruitment_id=second_job.pk).data["data"]["id"]
        now = clock.now()
        with self.freeze_at(now):
            self.client.post(f"{BASE}/{one}/messages", {"content": "较早"}, format="json")
        self.assertEqual([r["id"] for r in self.client.get(BASE).data["data"]["items"]], [one, two])
        with self.freeze_at(now + timedelta(seconds=1)):
            self.client.post(f"{BASE}/{two}/messages", {"content": "较新"}, format="json")
        self.assertEqual([r["id"] for r in self.client.get(BASE).data["data"]["items"]], [two, one])
        type(other).objects.filter(pk=other.pk).update(is_active=False)
        self.assertEqual(self.client.get(f"{BASE}/{two}/messages").status_code, 200)
        self.assertEqual(self.client.post(f"{BASE}/{two}/messages", {"content": "你好"}, format="json").status_code, 404)
