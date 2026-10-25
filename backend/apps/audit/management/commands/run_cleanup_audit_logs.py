"""预留审计日志留存清理命令，本周不执行清理或发送。"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """预留审计日志留存清理的命令入口。"""

    help = "预留审计日志留存清理（尚未实现）"

    def handle(self, *args, **options):
        """显式报错，避免预留命令被误认为已成功执行。"""
        raise CommandError("reserved")
