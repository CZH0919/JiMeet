from rest_framework.permissions import BasePermission

from apps.core.errors import Forbidden, NotAuthenticated


class IsAuthenticatedBiz(BasePermission):
    """要求用户已认证，未认证时抛出 BizError。"""
    def has_permission(self, request, view) -> bool:
        """
        Args:
            request: Django 请求对象
            view: DRF 视图对象
        Returns:
            bool: 用户是否有权限
        Raises:
            NotAuthenticated: 用户未认证 
        """
        user = request.user
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        return True


class IsAdminFlag(BasePermission):
    """要求用户已认证且 is_admin 为 True，未认证或非管理员时抛出 BizError。"""
    def has_permission(self, request, view) -> bool:
        """
        Args:
            request: Django 请求对象
            view: DRF 视图对象
        Returns:
            bool: 用户是否有权限
        Raises:
            NotAuthenticated: 用户未认证
            Forbidden: 用户非管理员
        """
        user = request.user
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        if not getattr(user, "is_admin", False):
            raise Forbidden("需要管理员权限")
        return True
