from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "业务通知邮件队列未启用"

    def handle(self, *args, **options):
        """保留命令名称，调用时返回非零退出码。"""
        raise CommandError("reserved")
