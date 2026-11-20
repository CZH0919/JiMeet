"""账号请求校验与本人资料输出，不在序列化器中查询数据库。"""
from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.accounts.identity import is_tongji_email
from apps.accounts.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from apps.core.choices import Role
from apps.core.serializers import StrictBooleanField, StrictCharField, StrictSerializer


class RegistrationEmailSerializer(StrictSerializer):
    """注册验证码仅接受规范化后域名精确匹配的同济邮箱。"""

    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        email = value.strip().lower()
        if email.rsplit("@", 1)[-1] != "tongji.edu.cn" or not is_tongji_email(email):
            raise serializers.ValidationError("须为 @tongji.edu.cn 邮箱")
        return email


class VerifyRegistrationCodeSerializer(RegistrationEmailSerializer):
    """验证码为六个 ASCII 数字组成的字符串，保留前导零。"""

    code = StrictCharField(
        min_length=6, max_length=6, trim_whitespace=False,
        validators=[RegexValidator(r"\A[0-9]{6}\Z", "请输入六位数字验证码")],
    )


class RegisterSerializer(StrictSerializer):
    """邮箱密码注册；密码策略由账号服务用 Django 验证器复核。"""

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH, trim_whitespace=False,
    )
    name = serializers.CharField(min_length=1, max_length=32)
    nickname = serializers.CharField(min_length=1, max_length=32, required=False)
    role = serializers.ChoiceField(choices=Role.values, required=False)


class LoginSerializer(StrictSerializer):
    """邮箱密码登录；密码不做长度下限，兼容历史账号。"""

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        max_length=MAX_PASSWORD_LENGTH, min_length=1, trim_whitespace=False,
    )


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
