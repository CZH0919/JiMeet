"""检测验证码 SMTP 服务及近期投递失败比例，不发送探测邮件。"""
from datetime import timedelta

from django.conf import settings
from django.core.mail import InvalidMailer, mailers
from django.core.mail.backends.smtp import EmailBackend
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q

from apps.accounts.models import RegistrationMailRequest
from apps.core import clock


class Command(BaseCommand):
    help = "检查验证码 SMTP 连接、认证和最近窗口内的已完成投递"

    def add_arguments(self, parser):
        parser.add_argument("--window-minutes", type=int, default=15)
        parser.add_argument("--min-attempts", type=int, default=5)
        parser.add_argument("--failure-percent", type=int, default=20)

    def handle(self, *args, **options):
        minutes, minimum, percent = (options[k] for k in ("window_minutes", "min_attempts", "failure_percent"))
        if not (1 <= minutes <= 1440 and minimum >= 1 and 1 <= percent <= 100):
            raise CommandError("窗口须为 1～1440 分钟，最小样本数须为正数，失败率阈值须为 1～100")
        if not settings.REGISTRATION_FROM_EMAIL or len(settings.REGISTRATION_HMAC_KEY) < 32:
            raise CommandError("验证码发信配置不完整")

        try:
            backend = mailers.create_connection("registration")
            if not isinstance(backend, EmailBackend) or not backend.use_ssl or not backend.username or not backend.password:
                raise CommandError("验证码发信通道需要启用 TLS 和 SMTP 认证")
            with backend:
                pass
        except (OSError, ValueError, InvalidMailer) as exc:
            raise CommandError(f"验证码 SMTP 不可用（{type(exc).__name__}）") from None

        now = clock.now()
        totals = RegistrationMailRequest.objects.filter(
            requested_at__gt=now - timedelta(minutes=minutes), requested_at__lte=now,
            delivered__isnull=False,
        ).aggregate(completed=Count("pk"), failed=Count("pk", filter=Q(delivered=False)))
        completed, failed = totals["completed"], totals["failed"]
        summary = f"最近 {minutes} 分钟，已完成 {completed} 次，失败 {failed} 次"
        if completed >= minimum and failed * 100 >= completed * percent:
            raise CommandError(f"验证码投递失败率达到 {percent}% 告警阈值：{summary}")
        self.stdout.write(f"验证码 SMTP 正常：{summary}")
