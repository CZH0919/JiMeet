from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "审计日志自动清理未启用"

    def handle(self, *args, **options):
        """保留命令名称，调用时返回非零退出码。"""
        raise CommandError("reserved")
