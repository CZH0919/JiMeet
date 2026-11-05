"""邮件发送与重试命令预留，调用显式失败以避免误报任务成功。"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """预留邮件发送与重试的命令入口。"""

    help = "预留邮件发送与重试（尚未实现）"

    def handle(self, *args, **options):
        """邮件发送与重试的预留命令入口。

        Args:
            args: Django 管理命令位置参数。
            options: Django 通用命令选项。

        Raises:
            CommandError: 功能尚未实现，当前始终返回 reserved 错误。
        """
        raise CommandError("reserved")
