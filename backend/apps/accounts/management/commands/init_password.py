"""历史账号密码初始化的受控管理命令。"""
import sys

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.audit import actions
from apps.audit.service import record


class Command(BaseCommand):
    """为无可用密码的历史账号初始化密码；新密码只从标准输入读取。

    不提供“仅凭邮箱重设密码”的公开入口，本命令仅供受控运维使用。
    """

    help = "初始化账号密码（新密码经标准输入传入，不走命令行参数）"

    def add_arguments(self, parser):
        """声明命令参数。

        Args:
            parser: argparse 解析器。
        """
        parser.add_argument("--email", required=True, help="目标账号邮箱")
        parser.add_argument(
            "--actor-email", default=None,
            help="可选：操作者账号邮箱，记入审计操作者；缺省时审计不带操作者",
        )

    def handle(self, *args, **options):
        """读取标准输入中的新密码，校验策略后哈希保存。

        Args:
            args: Django 位置参数。
            options: 命令选项，含 email 与 actor_email。

        Raises:
            CommandError: 账号不存在、密码为空或不合规。
        """
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError(f"账号不存在: {options['email']}")
        actor = None
        if options["actor_email"]:
            actor = User.objects.filter(email__iexact=options["actor_email"].strip()).first()
            if actor is None:
                raise CommandError(f"操作者账号不存在: {options['actor_email']}")
        self.stdout.write("请输入新密码（输入不回显）：")
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise CommandError("密码不能为空")
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError("密码不合规：" + "；".join(exc.messages)) from None
        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])
        record(
            actor=actor,
            action=actions.PASSWORD_INIT,
            target_type="user",
            target_id=user.pk,
            reason=f"管理命令初始化账号密码（目标 {user.email}）",
        )
        self.stdout.write(self.style.SUCCESS(f"已初始化账号密码: {user.email}"))
