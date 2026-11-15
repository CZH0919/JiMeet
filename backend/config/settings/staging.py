"""Dedicated, access-gated staging site. Never use this configuration for production."""
import os
from .base import *  # noqa: F401,F403
from .base import _env_bool, _env_list

DEBUG = False
MIDDLEWARE = ['apps.core.staging_middleware.StagingSessionStatusMiddleware', *MIDDLEWARE]
STAGING_LOGIN_ENABLED = True
ALLOW_DEV_LOGIN = True
STAGING_LOGIN_IDS = _env_list("STAGING_LOGIN_IDS")
if not STAGING_LOGIN_IDS:
    raise RuntimeError("Staging requires an explicit test identity allowlist")
for name in ("DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DB_NAME", "DB_USER", "DB_PASSWORD", "PRIVATE_FILE_ROOT"):
    if not os.environ.get(name):
        raise RuntimeError(f"Missing staging configuration: {name}")
if DATABASES["default"]["NAME"] != "jimeet_staging":
    raise RuntimeError("Staging must use its dedicated database")
SESSION_COOKIE_NAME = "jimeet_staging_session"
CSRF_COOKIE_NAME = "csrftoken"
SESSION_COOKIE_SECURE = _env_bool("STAGING_HTTPS", False)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
