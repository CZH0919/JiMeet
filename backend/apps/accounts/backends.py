"""认证 backend：SSO 身份交换与邮箱密码登录。"""
from django.contrib.auth.backends import ModelBackend
from django.db.models.functions import Lower

from apps.accounts.services import login_with_sso


class SSOBackend(ModelBackend):
    """将可信身份转换为用户，并复用 Django 的会话用户恢复行为。"""

    def authenticate(self, request, *, identity=None, **kwargs):
        """将已交换的身份交给账号服务认证。

        Args:
            request: 可选 Django 请求，当前实现不直接读取。
            identity: 可信 SSOIdentity；默认 None，此时跳过该 backend。
            kwargs: Django 传入的其他凭据，当前实现忽略。

        Returns:
            User | None: 已认证用户；未提供 identity 时返回 None，允许其他 backend 继续认证。

        Raises:
            BizError: 账号服务拒绝身份或账号已停用。
        """
        if identity is None:
            return None
        return login_with_sso(identity)


class EmailPasswordBackend(ModelBackend):
    """邮箱密码认证；只校验凭据本身，账号停用由调用方按 403 口径处理。

    返回已停用但凭据正确的用户是有意行为：登录接口须区分
    “凭据错误”（统一 401）与“凭据正确但账号停用”（403）。
    """

    def authenticate(self, request, *, email=None, password=None, **kwargs):
        """按规范化邮箱查找用户并校验密码。

        Args:
            request: 可选 Django 请求，当前实现不直接读取。
            email: 已去除首尾空白并小写化的邮箱。
            password: 原始密码；不接受空值或不可用密码。
            kwargs: Django 传入的其他凭据，当前实现忽略。

        Returns:
            User | None: 密码正确时返回用户（含已停用账号）；否则返回 None，不泄露账号是否存在。
        """
        from apps.accounts.models import User

        if not email or not password:
            return None
        user = (
            User.objects.annotate(email_lower=Lower("email"))
            .filter(email_lower=email)
            .first()
        )
        if user is None or not user.has_usable_password():
            return None
        if not user.check_password(password):
            return None
        return user
