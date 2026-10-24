"""预留邮件发送与重试命令，本周不执行清理或发送。"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """预留邮件发送与重试的命令入口。"""

    help = "预留邮件发送与重试（尚未实现）"

    def handle(self, *args, **options):
        """显式报错，避免预留命令被误认为已成功执行。"""
        raise CommandError("reserved")
