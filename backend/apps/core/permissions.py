from rest_framework.permissions import BasePermission

from apps.core.errors import Forbidden, NotAuthenticated


class IsAuthenticatedBiz(BasePermission):
    """要求用户已认证，未认证时抛出 BizError。"""
    def has_permission(self, request, view) -> bool:
        """校验会话身份是否已认证。

        Args:
            request: 带有当前 user 的 DRF 请求。
            view: 调用该权限检查的视图，当前实现不读取它。

        Returns:
            bool: 校验成功时为 True；拒绝时抛出异常。

        Raises:
            NotAuthenticated: 用户未认证。
        """
        user = request.user
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        return True


class IsAdminFlag(BasePermission):
    """要求用户已认证且 is_admin 为 True，未认证或非管理员时抛出 BizError。"""
    def has_permission(self, request, view) -> bool:
        """校验会话身份及业务管理员标记。

        Args:
            request: 带有当前 user 的 DRF 请求。
            view: 调用该权限检查的视图，当前实现不读取它。

        Returns:
            bool: 校验成功时为 True；拒绝时抛出异常。

        Raises:
            NotAuthenticated: 用户未认证。
            Forbidden: 用户没有 is_admin 标记；Django staff/superuser 标记不代替该标记。
        """
        user = request.user
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        if not getattr(user, "is_admin", False):
            raise Forbidden("需要管理员权限")
        return True
