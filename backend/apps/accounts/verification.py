"""新账号注册与登录的邮件验证码、发送配额及一次性核验资格。

验证码按用途（registration / login）、邮箱和会话三重绑定，均为 5 分钟有效；
同一邮箱的 60 秒重发间隔与发送额度在两种用途间共享。发码受理响应对新旧邮箱
一致并照常投递，是否已注册仅在原会话成功验码后提示。密码与验证码只保存安全
摘要，日志与接口响应不暴露原文。
"""
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
CODE_TTL = timedelta(minutes=5)
GRANT_TTL = timedelta(minutes=10)
RESEND_INTERVAL = timedelta(seconds=60)
MAX_FAILURES = 5
DAY = timedelta(days=1)
SESSION_MARKER = "registration_email_started"
PURPOSE_REGISTRATION = RegistrationVerification.PURPOSE_REGISTRATION
PURPOSE_LOGIN = RegistrationVerification.PURPOSE_LOGIN
_PURPOSE_TITLES = {
    PURPOSE_REGISTRATION: ("【济遇】注册邮箱验证码", "注册"),
    PURPOSE_LOGIN: ("【济遇】登录邮箱验证码", "登录"),
}


def _unavailable() -> BizError:
    return BizError("邮件发送服务暂时不可用，请稍后重试", code=ErrorCode.EMAIL_DELIVERY_UNAVAILABLE, http_status=503)


def _digest(purpose: str, value: str) -> str:
    """按用途隔离 HMAC 密钥空间，避免保存邮箱、IP、会话键和验证码原值。"""
    key = settings.REGISTRATION_HMAC_KEY
    if len(key) < 32:
        raise _unavailable()
    return salted_hmac(f"jimeet.registration.{purpose}", value, secret=key, algorithm="sha256").hexdigest()


def registration_session_key(session: SessionBase) -> str | None:
    """返回已开始邮箱验证且仍有效的 Django 会话键。"""
    return session.session_key if session.get(SESSION_MARKER) else None


def _reserve(
    purpose: str, email: str, ip: str, session: SessionBase,
) -> tuple[RegistrationVerification, RegistrationMailRequest]:
    """在短事务中分配滚动窗口额度及投递序号；已注册邮箱走同一路径。

    投递受理不区分邮箱是否已注册，避免暴露注册状态；重复注册提示由
    验码成功后的查询给出。
    """
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
        challenge, _ = RegistrationVerification.objects.update_or_create(
            purpose=purpose,
            email_key=email_key,
            session_key_hash=_digest("session", session.session_key),
            defaults={"latest_request": reservation},
        )
        return challenge, reservation


def _code_digest(challenge: RegistrationVerification, code: str) -> str:
    return _digest(
        "code", f"{challenge.purpose}:{challenge.email_key}:{challenge.session_key_hash}:{code}"
    )


def _send_code(*, purpose: str, email: str, ip: str, session: SessionBase) -> None:
    """向已规范化的同济邮箱投递六位码，绑定用途与当前会话。

    Raises:
        BizError: 超额返回 429，配置或投递不可用返回 503。
    """
    title, label = _PURPOSE_TITLES[purpose]
    if "registration" not in settings.MAILERS or not settings.REGISTRATION_FROM_EMAIL:
        raise _unavailable()
    challenge, reservation = _reserve(purpose, email, ip, session)
    number = secrets.randbelow(1_000_000)
    code = f"{number:06d}"
    if constant_time_compare(challenge.code_digest, _code_digest(challenge, code)):
        code = f"{(number + 1) % 1_000_000:06d}"
    try:
        sent = send_mail(
            title,
            f"你的济遇{label}验证码为 {code}，5 分钟内有效。请在申请验证码的页面输入。如非本人操作，可忽略本邮件。",
            settings.REGISTRATION_FROM_EMAIL, [email], using="registration",
        )
    except (OSError, ValueError, InvalidMailer) as exc:
        logger.warning("%s邮件投递失败（%s）", label, type(exc).__name__)
        raise _unavailable() from None
    if sent != 1:
        raise _unavailable()
    expiry = reservation.requested_at + CODE_TTL
    if clock.now() < expiry:
        RegistrationVerification.objects.filter(pk=challenge.pk, latest_request=reservation).update(
            code_digest=_code_digest(challenge, code), code_expires_at=expiry, failures=0,
            verified_at=None, duplicate_verified_at=None,
        )


def send_registration_code(*, email: str, ip: str, session: SessionBase) -> None:
    """投递注册验证码；已注册邮箱得到相同受理响应并照常收信。"""
    _send_code(purpose=PURPOSE_REGISTRATION, email=email, ip=ip, session=session)


def send_login_code(*, email: str, ip: str, session: SessionBase) -> None:
    """投递登录验证码；受理响应不区分邮箱是否已注册。"""
    _send_code(purpose=PURPOSE_LOGIN, email=email, ip=ip, session=session)


def _locked_challenge(
    purpose: str, email: str, session_key: str | None
) -> RegistrationVerification | None:
    if not session_key:
        return None
    return RegistrationVerification.objects.select_for_update().filter(
        purpose=purpose,
        email_key=_digest("email", email),
        session_key_hash=_digest("session", session_key),
    ).first()


def _check_code(challenge: RegistrationVerification | None, code: str, now: datetime) -> bool:
    """核对验证码并累计错码次数；连续错 5 次作废当前码。

    Returns:
        bool: 验证码正确且未过期时为 True。
    """
    if challenge and challenge.code_expires_at and now < challenge.code_expires_at:
        if constant_time_compare(challenge.code_digest, _code_digest(challenge, code)):
            return True
        challenge.failures += 1
        if challenge.failures >= MAX_FAILURES:
            challenge.code_digest = ""
            challenge.code_expires_at = None
        challenge.save(update_fields=["failures", "code_digest", "code_expires_at"])
    return False


def verify_registration_code(*, email: str, code: str, session_key: str | None) -> bool:
    """在原会话验证邮箱，返回该邮箱是否已有账号。

    Args:
        email: 规范化后的注册邮箱。
        code: 收件人提交的六位验证码。
        session_key: 发码会话的键。

    Returns:
        bool: 已有账号返回 True 并保存短时提示凭据，新邮箱返回 False 并取得一次性建号资格。

    Raises:
        ValidationFailed: 验证码错误、过期或与当前会话不匹配。
    """
    with transaction.atomic():
        challenge = _locked_challenge(PURPOSE_REGISTRATION, email, session_key)
        now = clock.now()
        if _check_code(challenge, code, now):
            exists = User.objects.filter(email__iexact=email).exists()
            challenge.code_digest = ""
            challenge.code_expires_at = None
            challenge.verified_at = None if exists else now
            challenge.duplicate_verified_at = now if exists else None
            challenge.save(update_fields=["code_digest", "code_expires_at", "verified_at", "duplicate_verified_at"])
            return exists
    raise ValidationFailed(details={"code": "验证码错误或已失效"})


def consume_login_code(*, email: str, code: str, session_key: str | None) -> None:
    """在登录事务中核对并一次性消费登录验证码。

    成功即删除该用途下会话-邮箱的验证码记录；失败累计错误次数并返回 400。

    Raises:
        ValidationFailed: 验证码错误、过期、已消费或会话不匹配。
    """
    with transaction.atomic():
        challenge = _locked_challenge(PURPOSE_LOGIN, email, session_key)
        now = clock.now()
        if _check_code(challenge, code, now):
            challenge.delete()
            return
    raise ValidationFailed(details={"code": "验证码错误或已失效"})


def consume_registration_grant(email: str, session_key: str | None) -> datetime:
    """在调用方的建号事务中消费资格并返回核验时间。

    Raises:
        ValidationFailed: 已验明邮箱属于已有账号，或没有匹配、有效的建号资格。
    """
    challenge = _locked_challenge(PURPOSE_REGISTRATION, email, session_key)
    now = clock.now()
    if challenge and challenge.duplicate_verified_at and now < challenge.duplicate_verified_at + GRANT_TTL:
        raise ValidationFailed(details={"email": "该邮箱已注册，请登录"})
    if not challenge or not challenge.verified_at or now >= challenge.verified_at + GRANT_TTL:
        raise ValidationFailed(details={"verification": "请先完成邮箱验证"})
    verified_at = challenge.verified_at
    challenge.delete()
    return verified_at
