"""上海时区自然月、到期读取边界及历史消息迁移。"""
from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.chat import selectors, services
from apps.chat.models import ChatConversation, ChatMessage
from tests.base import TxTestCase
from tests.factories import make_user


SHANGHAI = ZoneInfo("Asia/Shanghai")


class ChatRetentionTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.sender, self.recipient = sorted((make_user(), make_user()), key=lambda u: u.pk)
        self.conversation = ChatConversation.objects.create(user_low=self.sender, user_high=self.recipient)
        self.client.force_authenticate(user=self.recipient)
        self.base = "/api/v1/chat/conversations"
        self.path = f"{self.base}/{self.conversation.pk}"

    def test_month_end_cutoff_across_history_summary_count_and_receipt(self):
        sent = datetime(2026, 8, 31, 2, 15, tzinfo=SHANGHAI)
        due = datetime(2027, 2, 28, 2, 15, tzinfo=SHANGHAI)
        with self.freeze_at(sent):
            message, _ = services.send_message(self.sender, self.conversation.pk, content="月末消息")
        self.assertEqual(message.expires_at, due)
        for instant, count in ((due - timedelta(microseconds=1), 1), (due, 0)):
            with self.freeze_at(instant):
                self.assertEqual(self.client.get(self.path + "/messages").data["data"]["total"], count)
                summary = self.client.get(self.base).data["data"]["items"][0]
                self.assertEqual(summary["last_message"] is not None, bool(count))
                self.assertEqual(summary["unread_count"], count)
                self.assertEqual(self.client.get(self.base + "/unread-count").data["data"]["unread_count"], count)
        with self.freeze_at(due):
            self.assertEqual(self.client.post(self.path + "/read", {"message_ids": [message.pk]}, format="json").status_code, 404)
            self.assertTrue(ChatMessage.objects.filter(pk=message.pk, read_at__isnull=True).exists())
            log = StringIO()
            call_command("run_purge_chat_messages", batch_size=1, stdout=log)
            self.assertIn("1 条", log.getvalue())
            self.assertEqual(services.purge_expired_messages(), 0)
        self.assertFalse(ChatMessage.objects.exists())
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.last_message_at)

    def test_clipped_month_keeps_an_earlier_message_until_its_own_hour(self):
        early = datetime(2023, 8, 30, 23, 0, tzinfo=SHANGHAI)
        late = datetime(2023, 8, 31, 7, 0, tzinfo=SHANGHAI)
        with self.freeze_at(early):
            kept, _ = services.send_message(self.sender, self.conversation.pk, content="保留到当晚")
        with self.freeze_at(late):
            expired, _ = services.send_message(self.sender, self.conversation.pk, content="清晨到期")
        now = datetime(2024, 2, 29, 8, 0, tzinfo=SHANGHAI)
        with self.freeze_at(now):
            summary = self.client.get(self.base).data["data"]["items"][0]
            self.assertEqual((summary["last_message"]["id"], summary["unread_count"]), (kept.pk, 1))
            self.assertEqual(services.purge_expired_messages(), 1)
            self.assertFalse(ChatMessage.objects.filter(pk=expired.pk).exists())
            self.conversation.refresh_from_db()
            self.assertEqual(self.conversation.last_message_at, early)
            self.assertEqual(selectors.unread_total(self.recipient, now), 1)
        with self.assertRaises(CommandError):
            call_command("run_purge_chat_messages", batch_size=0)

    def test_migration_derives_expiry_for_existing_messages(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        previous = [("chat", "0001_initial")]
        executor.migrate(previous)
        old = executor.loader.project_state(previous).apps.get_model("chat", "ChatMessage")
        sent = datetime(2023, 12, 31, 22, 2, tzinfo=SHANGHAI)
        row = old.objects.create(conversation_id=self.conversation.pk, sender_id=self.sender.pk,
                                 created_at=sent, content="迁移样例")
        MigrationExecutor(connection).migrate(latest)
        final = ChatMessage.objects.get(pk=row.pk)
        self.assertEqual((final.content, final.created_at, final.read_at), ("迁移样例", sent, None))
        self.assertEqual(final.expires_at, datetime(2024, 6, 30, 22, 2, tzinfo=SHANGHAI))
