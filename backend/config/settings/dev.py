"""本地开发配置。"""
from .base import *  # noqa: F401,F403
from .base import _env_bool

DEBUG = _env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

ALLOW_DEV_LOGIN = _env_bool("ALLOW_DEV_LOGIN", True)

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
