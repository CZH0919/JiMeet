"""只接收已交换身份的认证 backend，密码认证保留给 ModelBackend。"""
from django.contrib.auth.backends import ModelBackend

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
