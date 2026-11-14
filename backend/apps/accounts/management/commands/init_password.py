"""历史账号密码初始化的受控管理命令。"""
import getpass
import sys
import warnings

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.passwords import MAX_PASSWORD_LENGTH, validate_new_password
from apps.audit import actions
from apps.audit.service import record


class Command(BaseCommand):
    """仅为无可用密码的账号初始化密码；终端输入不回显，也支持标准输入管道。"""

    help = "初始化历史账号密码（交互输入不回显，或从标准输入管道读取）"

    def add_arguments(self, parser):
        """声明目标邮箱及可选审计操作者，不接收密码参数。"""
        parser.add_argument("--email", required=True, help="目标账号邮箱")
        parser.add_argument(
            "--actor-email", default=None,
            help="可选：操作者账号邮箱，缺省时审计不带操作者",
        )

    def _read_password(self) -> str:
        """从终端或管道读取一行密码，保留密码本身的首尾空格。

        Returns:
            str: 不含行结束符的原始密码。

        Raises:
            CommandError: 输入中断或终端不能安全关闭回显。
        """
        try:
            if sys.stdin.isatty():
                with warnings.catch_warnings():
                    warnings.simplefilter("error", getpass.GetPassWarning)
                    return getpass.getpass("请输入新密码：", stream=self.stderr)
            return sys.stdin.readline(MAX_PASSWORD_LENGTH + 3).rstrip("\r\n")
        except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
            raise CommandError("未能安全读取密码，请重试或通过标准输入管道传入") from None

    def handle(self, *args, **options):
        """验证账号状态及密码策略，原子保存密码与审计。

        Args:
            args: Django 位置参数。
            options: email 指定目标，actor_email 可选指定审计操作者。

        Raises:
            CommandError: 账号不存在、已有可用密码、操作者不存在或密码不合规。
        """
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError(f"账号不存在: {options['email']}")
        if user.has_usable_password():
            raise CommandError("账号已有可用密码，不能重复初始化")
        password = self._read_password()
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=user.pk).first()
            if user is None:
                raise CommandError("目标账号已不存在")
            if user.has_usable_password():
                raise CommandError("账号已有可用密码，不能重复初始化")
            actor = None
            if options["actor_email"]:
                actor = User.objects.filter(email__iexact=options["actor_email"].strip()).first()
                if actor is None:
                    raise CommandError(f"操作者账号不存在: {options['actor_email']}")
            try:
                validate_new_password(password, user=user)
            except ValidationError as exc:
                raise CommandError("密码不合规：" + "；".join(exc.messages)) from None
            user.set_password(password)
            user.save(update_fields=["password", "updated_at"])
            record(
                actor=actor, action=actions.PASSWORD_INIT,
                target_type="user", target_id=user.pk,
                reason=f"管理命令初始化账号密码（目标 {user.email}）",
            )
        self.stdout.write(self.style.SUCCESS(f"已初始化账号密码: {user.email}"))
