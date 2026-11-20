"""新账号的邮件验证码、发送配额及一次性注册资格。"""
import logging
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
from django.core.mail import InvalidMailer, send_mail
from django.db import connection, transaction
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.accounts.models import RegistrationMailRequest, RegistrationVerification, User
from apps.core import clock
from apps.core.errors import BizError, ErrorCode, ValidationFailed

logger = logging.getLogger(__name__)
CODE_TTL = timedelta(minutes=10)
GRANT_TTL = timedelta(minutes=10)
RESEND_INTERVAL = timedelta(seconds=60)
MAX_FAILURES = 5
DAY = timedelta(days=1)
SESSION_MARKER = "registration_email_started"


def _unavailable() -> BizError:
    return BizError("注册邮件暂时不可用，请稍后重试", code=ErrorCode.EMAIL_DELIVERY_UNAVAILABLE, http_status=503)


def _digest(purpose: str, value: str) -> str:
    """按用途隔离 HMAC 密钥空间，避免保存邮箱、IP、会话键和验证码原值。"""
    key = settings.REGISTRATION_HMAC_KEY
    if len(key) < 32:
        raise _unavailable()
    return salted_hmac(f"jimeet.registration.{purpose}", value, secret=key, algorithm="sha256").hexdigest()


def registration_session_key(session: SessionBase) -> str | None:
    """返回已开始邮箱注册且仍有效的 Django 会话键。"""
    return session.session_key if session.get(SESSION_MARKER) else None


def _reserve(
    email: str, ip: str, session: SessionBase,
) -> tuple[RegistrationVerification, RegistrationMailRequest] | None:
    """在短事务中分配滚动窗口额度及投递序号，已注册邮箱也占用相同额度。"""
    email_key = _digest("email", email)
    ip_key = _digest("ip", ip)
    with transaction.atomic(durable=True):
        # 低频共享发件账号统一分配额度。锁在提交时释放，SMTP I/O 不占用数据库锁。
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [0x4A694D74, 1])
        now = clock.now()
        requests = RegistrationMailRequest.objects
        expired = requests.filter(requested_at__lte=now - DAY)
        RegistrationVerification.objects.filter(latest_request__in=expired).delete()
        expired.delete()
        mailbox = requests.filter(email_key=email_key)
        if (
            mailbox.filter(requested_at__gt=now - RESEND_INTERVAL).exists()
            or mailbox.count() >= settings.REGISTRATION_EMAIL_DAILY_LIMIT
            or requests.filter(ip_key=ip_key, requested_at__gt=now - timedelta(hours=1)).count()
            >= settings.REGISTRATION_IP_HOURLY_LIMIT
            or requests.count() >= settings.REGISTRATION_GLOBAL_DAILY_LIMIT
        ):
            raise BizError("验证码请求过于频繁，请稍后再试", code=ErrorCode.RATE_LIMITED, http_status=429)
        reservation = requests.create(email_key=email_key, ip_key=ip_key, requested_at=now)
        if not session.get(SESSION_MARKER):
            session[SESSION_MARKER] = True
        if not session.session_key:
            session.create()
        if User.objects.filter(email__iexact=email).exists():
            return None
        challenge, _ = RegistrationVerification.objects.update_or_create(
            email_key=email_key, session_key_hash=_digest("session", session.session_key),
            defaults={"latest_request": reservation},
        )
        return challenge, reservation


def _code_digest(challenge: RegistrationVerification, code: str) -> str:
    return _digest("code", f"{challenge.email_key}:{challenge.session_key_hash}:{code}")


def send_registration_code(*, email: str, ip: str, session: SessionBase) -> None:
    """向已规范化的可注册邮箱投递六位码，绑定当前会话。已注册邮箱得到相同受理响应。

    Args:
        email: 已规范化的同济邮箱。
        ip: 服务端连接的来源地址，用于发送额度控制。
        session: 浏览器的 Django 会话，首次受理时创建。

    Raises:
        BizError: 超额返回 429，配置或投递不可用返回 503。
    """
    if "registration" not in settings.MAILERS or not settings.REGISTRATION_FROM_EMAIL:
        raise _unavailable()
    reserved = _reserve(email, ip, session)
    if reserved is None:
        return
    challenge, reservation = reserved
    number = secrets.randbelow(1_000_000)
    code = f"{number:06d}"
    if constant_time_compare(challenge.code_digest, _code_digest(challenge, code)):
        code = f"{(number + 1) % 1_000_000:06d}"
    try:
        sent = send_mail(
            "【济遇】注册邮箱验证码",
            f"你的济遇注册验证码为 {code}，10 分钟内有效。请在申请验证码的页面输入。如非本人操作，可忽略本邮件。",
            settings.REGISTRATION_FROM_EMAIL, [email], using="registration",
        )
    except (OSError, ValueError, InvalidMailer) as exc:
        logger.warning("注册邮件投递失败（%s）", type(exc).__name__)
        raise _unavailable() from None
    if sent != 1:
        raise _unavailable()
    expiry = reservation.requested_at + CODE_TTL
    if clock.now() < expiry:
        RegistrationVerification.objects.filter(pk=challenge.pk, latest_request=reservation).update(
            code_digest=_code_digest(challenge, code), code_expires_at=expiry, failures=0, verified_at=None,
        )


def _locked_challenge(email: str, session_key: str | None) -> RegistrationVerification | None:
    if not session_key:
        return None
    return RegistrationVerification.objects.select_for_update().filter(
        email_key=_digest("email", email), session_key_hash=_digest("session", session_key),
    ).first()


def verify_registration_code(*, email: str, code: str, session_key: str | None) -> None:
    """在原会话中校验邮箱验证码。成功生成短时注册资格，失败累计错误次数并返回 400。"""
    with transaction.atomic():
        challenge = _locked_challenge(email, session_key)
        now = clock.now()
        if challenge and challenge.code_expires_at and now < challenge.code_expires_at:
            if constant_time_compare(challenge.code_digest, _code_digest(challenge, code)):
                challenge.code_digest = ""
                challenge.code_expires_at = None
                challenge.verified_at = now
                challenge.save(update_fields=["code_digest", "code_expires_at", "verified_at"])
                return
            challenge.failures += 1
            if challenge.failures >= MAX_FAILURES:
                challenge.code_digest = ""
                challenge.code_expires_at = None
            challenge.save(update_fields=["failures", "code_digest", "code_expires_at"])
    raise ValidationFailed(details={"code": "验证码错误或已失效"})


def consume_registration_grant(email: str, session_key: str | None) -> datetime:
    """在调用方的建号事务中消费资格并返回核验时间。

    Raises:
        ValidationFailed: 邮箱与会话没有匹配资格或资格已过期。
    """
    challenge = _locked_challenge(email, session_key)
    if not challenge or not challenge.verified_at or clock.now() >= challenge.verified_at + GRANT_TTL:
        raise ValidationFailed(details={"verification": "请先完成邮箱验证"})
    verified_at = challenge.verified_at
    challenge.delete()
    return verified_at
