"""账号登录、个人资料与隐私确认服务。"""
from django.db import IntegrityError, transaction

from apps.accounts.identity import is_tongji_email, resolve_role
from apps.accounts.models import User
from apps.accounts.sso import SSOIdentity
from apps.core import clock
from apps.core.errors import BizError, ErrorCode, Forbidden, ValidationFailed


def _auth_failed() -> BizError:
    """构造不泄露身份冲突细节的认证失败异常。

    Returns:
        BizError: AUTH_FAILED、HTTP 401；由调用方决定何时抛出。
    """
    return BizError("认证身份无效或存在冲突", code=ErrorCode.AUTH_FAILED, http_status=401)


def login_with_sso(identity: SSOIdentity) -> User:
    """按可信身份标识查找、绑定或创建用户。

    查找及绑定在事务中执行；不会把已绑定 subject 改绑到其他账号。

    Args:
        identity: SSOIdentity，含非空且长度合法的 subject、real_id、name 和允许域名的 email。

    Returns:
        User: 已启用的用户；重复登录保留已有昵称和资料。

    Raises:
        BizError: 身份无效、标识冲突或唯一约束冲突，错误码 AUTH_FAILED。
        Forbidden: 命中已停用账号。
    """
    values = (identity.real_id, identity.name, identity.email, identity.subject)
    limits = (32, 32, 254, 191)
    # 在查询或写库前校验身份字段，避免通过约束错误暴露冲突信息。
    if any(not isinstance(value, str) or not value.strip() or len(value.strip()) > limit
           for value, limit in zip(values, limits)):
        raise _auth_failed()
    real_id, name, email, subject = (value.strip() for value in values)
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
                        real_id=real_id, name=name, email=email,
                        role=resolve_role(real_id), sso_subject=subject, is_admin=False,
                    )
            if not user.is_active:
                raise Forbidden("账号已停用")
            return user
    except IntegrityError:
        # 包括邮箱冲突和并发首次登录唯一约束冲突，不向客户端泄露数据库信息。
        raise _auth_failed() from None


def update_profile(user: User, nickname=None, email_notify_enabled=None) -> User:
    """更新本人昵称和邮件通知偏好。

    Args:
        user: 待更新的用户对象，访问身份由调用方保证。
        nickname: 可选字符串；去除首尾空白后须为 1～32 字，None 表示不修改。
        email_notify_enabled: 可选 bool；None 表示不修改，不能用字符串或数字代替。

    Returns:
        User: 原用户对象，包含已保存的新值；没有提供字段时不写数据库。

    Raises:
        ValidationFailed: 昵称或通知开关类型、取值不合法。
    """
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
    """记录首次隐私告知确认，重复调用保留首次时间。

    Args:
        user: 已明确确认隐私告知的当前用户。

    Returns:
        User: 已从数据库刷新确认状态的原用户对象。
    """
    now = clock.now()
    User.objects.filter(pk=user.pk, privacy_consented_at__isnull=True).update(
        privacy_consented_at=now, updated_at=now,
    )
    user.refresh_from_db()
    return user
