"""分批清理到期聊天消息。"""
from django.core.management.base import BaseCommand, CommandError

from apps.chat.services import purge_expired_messages


class Command(BaseCommand):
    help = "删除自发送时刻起已满六个自然月的聊天消息，保留会话"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500, help="每批消息数，默认 500")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if not 1 <= batch_size <= 5000:
            raise CommandError("每批消息数须在 1～5000 之间")
        count = purge_expired_messages(batch_size=batch_size)
        self.stdout.write(f"已清理 {count} 条到期聊天消息")
