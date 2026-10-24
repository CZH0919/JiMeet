"""账号登录、个人资料与隐私确认服务。"""
from django.db import IntegrityError, transaction

from apps.accounts.identity import is_tongji_email, resolve_role
from apps.accounts.models import User
from apps.accounts.sso import SSOIdentity
from apps.core import clock
from apps.core.errors import BizError, ErrorCode, Forbidden, ValidationFailed


def _auth_failed() -> BizError:
    """
    返回统一认证失败，避免暴露冲突账号的具体资料。
    Raises:
        BizError: 认证失败错误
    """
    return BizError("认证身份无效或存在冲突", code=ErrorCode.AUTH_FAILED, http_status=401)


def login_with_sso(identity: SSOIdentity) -> User:
    """
    按 subject、编号依次查找或绑定账号，不覆盖已绑定的其他身份。
    Args:
        identity: 已交换的 SSOIdentity 对象
    Returns:
        用户对象
    Raises:
        BizError: 认证失败错误
    """
    values = (identity.real_id, identity.name, identity.email, identity.subject)
    limits = (32, 32, 254, 191)
    # 如果任意字段不属于实例，为空或超长，则拒绝登录，避免数据库约束错误泄露信息。
    if any(not isinstance(value, str) or not value.strip() or len(value.strip()) > limit
           for value, limit in zip(values, limits)):
        raise _auth_failed()
    real_id, name, email, subject = (value.strip() for value in values) # 确认没问题后，才传递参数
    if not is_tongji_email(email):
        raise _auth_failed()
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().filter(sso_subject=subject).first()
            if user is not None:
                # 稳定 subject 不得被用于登录另一个编号的账号。
                if user.real_id != real_id:
                    raise _auth_failed()
            else:
                user = User.objects.select_for_update().filter(real_id=real_id).first()
                if user is not None:
                    if user.sso_subject is not None:
                        raise _auth_failed()
                    if not user.is_active:
                        raise Forbidden("账号已停用")
                    user.sso_subject = subject
                    user.save(update_fields=["sso_subject", "updated_at"])
                else:
                    user = User.objects.create_user(
                        real_id=real_id, name=name, email=email, nickname=name,
                        role=resolve_role(real_id), sso_subject=subject, is_admin=False,
                    )
            if not user.is_active:
                raise Forbidden("账号已停用")
            return user
    except IntegrityError:
        # 包括邮箱冲突和并发首次登录唯一约束冲突，不向客户端泄露数据库信息。
        raise _auth_failed() from None


def update_profile(user: User, nickname=None, email_notify_enabled=None) -> User:
    """只更新昵称与邮件开关；省略的字段保持原值。"""
    fields = []
    if nickname is not None:
        if not isinstance(nickname, str) or not 1 <= len(nickname.strip()) <= 32:
            raise ValidationFailed(details={"nickname": "昵称须为 1 至 32 字"})
        fields.append("nickname")
    if email_notify_enabled is not None:
        if type(email_notify_enabled) is not bool:
            raise ValidationFailed(details={"email_notify_enabled": "须为布尔值"})
        fields.append("email_notify_enabled")
    # 所有参数校验完成后再修改对象，避免失败调用留下部分内存变更。
    if "nickname" in fields:
        user.nickname = nickname.strip()
    if "email_notify_enabled" in fields:
        user.email_notify_enabled = email_notify_enabled
    if fields:
        user.save(update_fields=[*fields, "updated_at"])
    return user


def give_privacy_consent(user: User) -> User:
    """
    将用户的隐私协议同意标记设为当前时间，若已同意则不变。
    仅在用户明确同意时调用，避免误操作覆盖原值。
    Args:
        user: 用户对象
    Returns:
        用户对象
    """
    now = clock.now()
    User.objects.filter(pk=user.pk, privacy_consented_at__isnull=True).update(
        privacy_consented_at=now, updated_at=now,
    )
    user.refresh_from_db()
    return user
