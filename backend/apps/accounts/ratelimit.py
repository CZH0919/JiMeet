"""注册/登录失败限流：数据库计数，窗口滑过自动恢复。

阈值与窗口见 file/tasks/修订说明与待确认事项.md 2.1：
600 秒窗口内同一邮箱键 5 次、同一来源 IP 键 20 次失败后拒绝后续请求。
计数键只保存 SHA-256 摘要，不落明文邮箱；计数采用 INSERT，不读改写，保证并发失败不丢计数。
"""
import hashlib
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from apps.accounts.models import AuthFailure
from apps.core import clock
from apps.core.errors import BizError, ErrorCode

WINDOW = timedelta(seconds=600)
LIMITS = {"email": 5, "ip": 20}
KIND_LOGIN = "login"
KIND_REGISTER = "register"


def normalize_email_key(value) -> str:
    """提取可计数的邮箱键，格式无效时返回空字符串。

    Args:
        value: 原始邮箱字段，允许缺失或类型错误。

    Returns:
        str: 合法邮箱去除首尾空白并小写化后的值；无效时不建立邮箱键。
    """
    if not isinstance(value, str):
        return ""
    normalized = value.strip().lower()
    if len(normalized) > 254:
        return ""
    try:
        validate_email(normalized)
    except ValidationError:
        return ""
    return normalized


def check_auth_limits(*, email: str, ip: str, kind: str) -> None:
    """检查一次认证尝试的 IP 与邮箱失败额度。

    Args:
        email: 规范化邮箱；不可解析时为空字符串。
        ip: 来源 IP，缺失时为空字符串。
        kind: login 或 register，两种操作分别计数。

    Raises:
        BizError: 任一额度已耗尽，返回 429 RATE_LIMITED。
    """
    check_limit(scope="ip", value=ip, kind=kind)
    check_limit(scope="email", value=email, kind=kind)


def record_auth_failure(*, email: str, ip: str, kind: str) -> None:
    """在同一事务内分别累计一次邮箱和 IP 失败，不记录请求内容。

    Args:
        email: 规范化邮箱；不可解析时为空字符串。
        ip: 来源 IP，缺失时为空字符串。
        kind: login 或 register。
    """
    with transaction.atomic():
        record_failure(scope="email", value=email, kind=kind)
        record_failure(scope="ip", value=ip, kind=kind)


def _key_hash(scope: str, value: str) -> str:
    """计算限流键摘要，邮箱与 IP 的键空间互相隔离。

    Args:
        scope: 键类型，email 或 ip。
        value: 键原值（规范化邮箱或来源 IP）。

    Returns:
        str: 64 位十六进制 SHA-256 摘要。
    """
    return hashlib.sha256(f"{scope}:{value}".encode("utf-8")).hexdigest()


def check_limit(*, scope: str, value: str, kind: str) -> None:
    """超出失败阈值时拒绝请求。

    Args:
        scope: 键类型，email 或 ip。
        value: 键原值。
        kind: 操作类型，login 或 register。

    Raises:
        BizError: 窗口内失败次数已达阈值，RATE_LIMITED、HTTP 429。
    """
    if not value:
        return
    window_start = clock.now() - WINDOW
    count = AuthFailure.objects.filter(
        key_hash=_key_hash(scope, value), kind=kind, created_at__gte=window_start
    ).count()
    if count >= LIMITS[scope]:
        raise BizError(
            "尝试次数过多，请稍后再试", code=ErrorCode.RATE_LIMITED, http_status=429
        )


def record_failure(*, scope: str, value: str, kind: str) -> None:
    """记录一次失败并顺带清理该键的窗口外记录。

    Args:
        scope: 键类型，email 或 ip。
        value: 键原值。
        kind: 操作类型，login 或 register。
    """
    if not value:
        return
    key_hash = _key_hash(scope, value)
    AuthFailure.objects.create(key_hash=key_hash, kind=kind, created_at=clock.now())
    AuthFailure.objects.filter(
        key_hash=key_hash, created_at__lt=clock.now() - WINDOW
    ).delete()


def clear_failures(*, scope: str, value: str, kind: str) -> None:
    """成功注册或登录后清除对应键的失败计数。

    Args:
        scope: 键类型，email 或 ip。
        value: 键原值。
        kind: 操作类型，login 或 register。
    """
    if not value:
        return
    AuthFailure.objects.filter(key_hash=_key_hash(scope, value), kind=kind).delete()
