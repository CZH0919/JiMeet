"""只接收已交换身份的认证 backend，密码认证保留给 ModelBackend。"""
from django.contrib.auth.backends import ModelBackend

from apps.accounts.services import login_with_sso


class SSOBackend(ModelBackend):
    """将可信身份转换为用户，并复用 Django 的会话用户恢复行为。"""

    def authenticate(self, request, *, identity=None, **kwargs):
        """
        不接收身份时跳过，避免截获 Django Admin 的密码登录。

        Args:
            request: Django 请求对象
            identity: 已交换的 SSOIdentity 对象
        Returns:
            用户对象或 None
        """
        if identity is None:
            return None
        return login_with_sso(identity)
