from rest_framework.permissions import BasePermission

from apps.core.errors import Forbidden, NotAuthenticated


class IsAuthenticatedBiz(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        return True


class IsAdminFlag(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        if not getattr(user, "is_admin", False):
            raise Forbidden("需要管理员权限")
        return True
