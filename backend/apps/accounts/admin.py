from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.accounts.models import User


class AccountCreationForm(UserCreationForm):
    """后台创建用户表单，沿用 Django 密码校验与哈希保存逻辑。"""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("real_id", "name", "email", "nickname", "role")


class AccountChangeForm(UserChangeForm):
    """后台用户编辑表单，密码以 Django 的只读哈希摘要展示。"""

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    用户后台管理入口，维护用户资料与业务管理员标记 is_admin。

    is_staff / is_superuser / groups / user_permissions 仅管理 Django Admin
    访问权限，业务权限仍只依据 is_admin。
    """

    form = AccountChangeForm
    add_form = AccountCreationForm
    list_display = ("id", "real_id", "name", "nickname", "role", "is_admin", "is_active")
    list_filter = ("role", "is_admin", "is_active", "is_staff")
    search_fields = ("real_id", "name", "nickname", "email")
    ordering = ("id",)
    readonly_fields = ("uid", "last_login", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("real_id", "password")}),
        (
            "个人资料",
            {"fields": ("uid", "name", "nickname", "email", "role", "sso_subject")},
        ),
        (
            "业务权限与偏好",
            {"fields": ("is_active", "is_admin", "email_notify_enabled", "privacy_consented_at")},
        ),
        (
            "Django 后台权限",
            {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("时间", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": (
            "real_id", "name", "email", "nickname", "role", "password1", "password2",
            "is_active", "is_admin", "is_staff", "is_superuser",
        )}),
    )
