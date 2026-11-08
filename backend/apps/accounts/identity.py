"""身份规则；学校正式编号规范确认前仅供开发使用。"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.core.choices import Role


def resolve_role(real_id: str) -> str:
    """按开发编号前缀映射学生或教师身份。

    该规则仅用于开发身份，正式身份来源尚未接入。

    Args:
        real_id: 已校验的编号字符串；以 t/T 开头时映射为教师。

    Returns:
        Role: TEACHER 或 STUDENT。
    """
    return Role.TEACHER if real_id.lower().startswith("t") else Role.STUDENT


def is_tongji_email(email: str) -> bool:
    """检查邮箱格式及配置允许的完整域名。

    Args:
        email: 待检查的邮箱值。

    Returns:
        bool: 格式有效且域名精确匹配 ALLOWED_EMAIL_DOMAINS 时为 True；非字符串或无效邮箱为 False。
    """
    if not isinstance(email, str):
        return False
    try:
        validate_email(email)
    except ValidationError:
        return False
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in {value.lower() for value in settings.ALLOWED_EMAIL_DOMAINS}
