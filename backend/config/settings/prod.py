"""生产配置：缺失关键环境变量时直接启动失败，不做静默降级。"""
import os

from .base import *  # noqa: F401,F403

DEBUG = False
ALLOW_DEV_LOGIN = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 3600
# 仅在上游通过受限 Unix 套接字连接且覆盖转发头时启用。
TRUST_HTTPS_PROXY = os.environ.get("JIMEET_TRUST_HTTPS_PROXY") == "1"
if TRUST_HTTPS_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

_REQUIRED_ENV = (
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
)

_missing = [name for name in _REQUIRED_ENV if not os.environ.get(name)]
if _missing:
    raise RuntimeError(f"生产配置缺少必需的环境变量: {', '.join(_missing)}")

if os.environ.get("ALLOW_DEV_LOGIN", "").strip().lower() in {"1", "true", "yes", "on"}:
    raise RuntimeError("生产环境禁止开启 ALLOW_DEV_LOGIN")
