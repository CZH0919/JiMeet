"""受控授予业务管理员权限的管理命令。"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.audit import actions
from apps.audit.service import record


class Command(BaseCommand):
    """按邮箱为已有账号授予业务管理员权限（is_admin），并写审计。"""

    help = "按邮箱授予业务管理员权限（受控操作，写审计）"

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
        """锁定目标账号，同事务授予权限并写审计；已授权时不重复变更。

        Args:
            args: Django 位置参数。
            options: 命令选项，含 email 与 actor_email。

        Raises:
            CommandError: 目标账号或操作者账号不存在。
        """
        with transaction.atomic():
            user = User.objects.select_for_update().filter(email__iexact=options["email"].strip()).first()
            if user is None:
                raise CommandError(f"账号不存在: {options['email']}")
            actor = None
            if options["actor_email"]:
                actor = User.objects.filter(email__iexact=options["actor_email"].strip()).first()
                if actor is None:
                    raise CommandError(f"操作者账号不存在: {options['actor_email']}")
            if user.is_admin:
                self.stdout.write(f"账号已具备管理员权限，无变更: {user.email}")
                return
            user.is_admin = True
            user.save(update_fields=["is_admin", "updated_at"])
            record(
                actor=actor,
                action=actions.ADMIN_GRANT,
                target_type="user",
                target_id=user.pk,
                reason=f"管理命令授予管理员权限（目标 {user.email}）",
            )
        self.stdout.write(self.style.SUCCESS(f"已授予管理员权限: {user.email}"))
