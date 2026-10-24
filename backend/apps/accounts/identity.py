"""身份规则；学校正式编号规范确认前仅供开发使用。"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.core.choices import Role


def resolve_role(real_id: str) -> str:
    """
    按临时编号前缀解析身份，正式接入前必须替换。
    """
    # TODO(规则待定)：不得把这个开发期前缀规则直接带入生产。
    return Role.TEACHER if real_id.lower().startswith("t") else Role.STUDENT


def is_tongji_email(email: str) -> bool:
    """
    先校验邮箱格式，再精确匹配允许域名，不接受相似后缀。
    """
    if not isinstance(email, str):
        return False
    try:
        validate_email(email)
    except ValidationError:
        return False
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in {value.lower() for value in settings.ALLOWED_EMAIL_DOMAINS}
