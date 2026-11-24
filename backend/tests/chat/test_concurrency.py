"""PostgreSQL 上验证双向建会话、跨会话发送额度、回执及消息事务。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.db import DatabaseError, close_old_connections, connections

from apps.chat import selectors, services
from apps.chat.models import ChatConversation, ChatMessage, ChatSendPause
from apps.core import clock
from apps.core.errors import BizError
from tests.base import TxTestCase
from tests.factories import make_recruitment, make_user


class ChatConcurrencyTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.sender, self.peer = make_user(), make_user()
        self.job = make_recruitment(self.peer)

    def parallel(self, *operations):
        gate = Barrier(len(operations))

        def invoke(operation):
            close_old_connections()
            try:
                gate.wait(timeout=8)
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(invoke, operation) for operation in operations]
            return [f.result(timeout=15) for f in futures]

    def open(self, peer, job):
        return services.open_conversation(self.sender, peer_uid=peer.uid, recruitment_id=job.pk)[0]

    def fill(self, conversation, moment, count):
        ChatMessage.objects.bulk_create([
            ChatMessage(sender=self.sender, conversation=conversation, content="预约讨论", created_at=moment)
            for _ in range(count)
        ])

    def test_simultaneous_opposite_directions_create_one_conversation(self):
        own_job = make_recruitment(self.sender)
        first = lambda: services.open_conversation(self.sender, peer_uid=self.peer.uid, recruitment_id=self.job.pk)
        reverse = lambda: services.open_conversation(self.peer, peer_uid=self.sender.uid, recruitment_id=own_job.pk)
        results = self.parallel(first, reverse, first)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len({row.pk for row, _ in results}), 1)
        self.assertEqual(ChatConversation.objects.count(), 1)

    def test_cross_conversation_last_slot_and_fixed_pause(self):
        one = self.open(self.peer, self.job)
        another = make_user()
        two = self.open(another, make_recruitment(another))
        now = clock.now()
        self.fill(one, now - timedelta(seconds=25), 49)

        def send(conversation):
            try:
                services.send_message(self.sender, conversation.pk, content="第 50 条")
                return 201
            except BizError as exc:
                return exc.http_status

        with self.freeze_at(now):
            self.assertEqual(sorted(self.parallel(lambda: send(one), lambda: send(two))), [201, 429])
            self.assertEqual(ChatMessage.objects.filter(sender=self.sender).count(), 50)
            self.assertEqual(ChatSendPause.objects.get(user=self.sender).blocked_until, now + timedelta(minutes=1))
            services.send_message(self.peer, one.pk, content="另一位发送者可发送")
        self.client.force_authenticate(user=self.sender)
        url = f"/api/v1/chat/conversations/{two.pk}/messages"
        with self.freeze_at(now + timedelta(seconds=59, milliseconds=500)):
            limited = self.client.post(url, {"content": "重试"}, format="json")
            self.assertEqual((limited.status_code, limited.data["code"], limited.data["data"]["details"]["retry_after"]),
                             (429, "RATE_LIMITED", 1))
        self.assertEqual(ChatSendPause.objects.get(user=self.sender).blocked_until, now + timedelta(minutes=1))
        with self.freeze_at(now + timedelta(minutes=1)):
            self.assertEqual(self.client.post(url, {"content": "恢复发送"}, format="json").status_code, 201)

    def test_window_excludes_the_exact_previous_minute(self):
        conversation = self.open(self.peer, self.job)
        now = clock.now()
        self.fill(conversation, now - timedelta(minutes=1), 50)
        with self.freeze_at(now):
            services.send_message(self.sender, conversation.pk, content="新窗口")
        self.assertFalse(ChatSendPause.objects.exists())

    def test_new_message_during_receipt_remains_unread(self):
        conversation = self.open(self.peer, self.job)
        before, _ = services.send_message(self.sender, conversation.pk, content="已展示")
        new, marked = self.parallel(
            lambda: services.send_message(self.sender, conversation.pk, content="新到达")[0],
            lambda: services.mark_messages_read(self.peer, conversation.pk, message_ids=[before.pk]),
        )
        self.assertEqual(marked, 1)
        before.refresh_from_db()
        new.refresh_from_db()
        self.assertIsNotNone(before.read_at)
        self.assertIsNone(new.read_at)
        self.assertEqual(selectors.unread_total(self.peer, clock.now()), 1)

    def test_cleanup_and_send_preserve_newest_message(self):
        conversation = self.open(self.peer, self.job)
        now = clock.now()
        self.fill(conversation, now - timedelta(days=240), 1)
        with self.freeze_at(now):
            deleted, new = self.parallel(
                lambda: services.purge_expired_messages(batch_size=1),
                lambda: services.send_message(self.sender, conversation.pk, content="仍有效的消息")[0],
            )
        conversation.refresh_from_db()
        self.assertEqual((deleted, conversation.last_message_at), (1, now))
        self.assertEqual(list(ChatMessage.objects.values_list("pk", flat=True)), [new.pk])

    def test_storage_failure_logs_only_identifiers(self):
        conversation = self.open(self.peer, self.job)
        self.client.force_authenticate(user=self.sender)
        text = "存储失败的测试正文"
        with self.assertLogs("apps.chat.services", level="ERROR") as captured:
            with patch.object(ChatMessage.objects, "create", side_effect=DatabaseError(text)):
                response = self.client.post(f"/api/v1/chat/conversations/{conversation.pk}/messages",
                                            {"content": text}, format="json")
        self.assertEqual((response.status_code, response.data["code"]), (500, "INTERNAL_ERROR"))
        self.assertNotIn(text, str(captured.output))
        self.assertNotIn(text, response.content.decode())
        self.assertFalse(ChatMessage.objects.exists())

    def test_failed_activity_update_rolls_back_message(self):
        conversation = self.open(self.peer, self.job)
        with patch.object(ChatConversation, "save", side_effect=RuntimeError("测试事务回滚")):
            with self.assertRaises(RuntimeError):
                services.send_message(self.sender, conversation.pk, content="事务消息")
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatSendPause.objects.exists())
        conversation.refresh_from_db()
        self.assertIsNone(conversation.last_message_at)
