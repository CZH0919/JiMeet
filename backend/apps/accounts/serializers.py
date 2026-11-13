"""账号请求校验与本人资料输出，不在序列化器中查询数据库。"""
from rest_framework import serializers

from apps.core.choices import Role
from apps.core.serializers import StrictBooleanField, StrictSerializer


class RegisterSerializer(StrictSerializer):
    """邮箱密码注册；密码策略由账号服务用 Django 验证器复核。"""

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False)
    name = serializers.CharField(min_length=1, max_length=32)
    nickname = serializers.CharField(min_length=1, max_length=32, required=False)
    role = serializers.ChoiceField(choices=Role.values, required=False)


class LoginSerializer(StrictSerializer):
    """邮箱密码登录；密码不做长度下限，兼容历史账号。"""

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, min_length=1, trim_whitespace=False)


class DevLoginSerializer(StrictSerializer):
    """开发登录只允许编号及可选姓名、邮箱。"""

    real_id = serializers.RegexField(r"^[A-Za-z0-9_-]+$", max_length=32)
    name = serializers.CharField(max_length=32, required=False)
    email = serializers.EmailField(max_length=254, required=False)


class ProfileUpdateSerializer(StrictSerializer):
    """允许修改的个人资料字段。"""

    nickname = serializers.CharField(min_length=1, max_length=32, required=False)
    email_notify_enabled = StrictBooleanField(required=False)


def profile_data(user) -> dict:
    """序列化当前用户自己的资料。

    包含姓名和邮箱，只用于本人资料或登录响应，不用作公开用户摘要。

    Args:
        user: 已认证的本人 User 实例。

    Returns:
        dict: uid、nickname、name、email、role、is_admin、email_notify_enabled、privacy_consented。
    """
    return {
        "uid": user.uid, "nickname": user.nickname, "name": user.name,
        "role": user.role, "is_admin": user.is_admin, "email": user.email,
        "email_notify_enabled": user.email_notify_enabled,
        "privacy_consented": user.privacy_consented_at is not None,
    }
