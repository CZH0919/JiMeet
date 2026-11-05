"""孤立简历任务清理命令预留，调用显式失败以避免误报任务成功。"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """预留孤立简历文件清理的命令入口。"""

    help = "预留孤立简历文件清理（尚未实现）"

    def handle(self, *args, **options):
        """孤立简历任务清理的预留命令入口。

        Args:
            args: Django 管理命令位置参数。
            options: Django 通用命令选项。

        Raises:
            CommandError: 功能尚未实现，当前始终返回 reserved 错误。
        """
        raise CommandError("reserved")
