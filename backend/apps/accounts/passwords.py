"""注册与历史账号初始化共用的新密码策略。"""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def validate_new_password(password: str, *, user) -> None:
    """校验新密码长度及 Django 配置的密码策略。

    Args:
        password: 原始密码，保留首尾空白，不进行规范化。
        user: 包含邮箱、姓名的用户实例，可尚未保存。

    Raises:
        ValidationError: 密码不是字符串、长度超限或未通过密码验证器。
    """
    if not isinstance(password, str):
        raise ValidationError("密码须为字符串", code="password_invalid")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValidationError("密码长度须为 8 至 128 字符", code="password_length")
    validate_password(password, user=user)
