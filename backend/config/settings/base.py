"""公共配置。环境相关项由 dev/prod/test 覆盖。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def _env(name, default=None):
    return os.environ.get(name, default)


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name, default=""):
    return [item.strip() for item in _env(name, default).split(",") if item.strip()]


SECRET_KEY = _env("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key")
DEBUG = False
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.recruitments",
    "apps.applications",
    "apps.notifications",
    "apps.files",
    "apps.chat",
    "apps.audit",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _env("DB_NAME", "jimeet"),
        "USER": _env("DB_USER", "jimeet"),
        "PASSWORD": _env("DB_PASSWORD", "jimeet"),
        "HOST": _env("DB_HOST", "127.0.0.1"),
        "PORT": _env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# 事务由 service 层显式开启，不依赖隐式请求级事务。
ATOMIC_REQUESTS = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "var" / "static"
MEDIA_ROOT = BASE_DIR / "var" / "media"

# 简历等私有文件目录，不在任何静态/媒体 URL 映射之下。
PRIVATE_FILE_ROOT = Path(_env("PRIVATE_FILE_ROOT", BASE_DIR / "var" / "private"))

MAX_HEADCOUNT_LIMIT = 50
ALLOWED_EMAIL_DOMAINS = _env_list("ALLOWED_EMAIL_DOMAINS", "tongji.edu.cn")
ALLOW_DEV_LOGIN = _env_bool("ALLOW_DEV_LOGIN", False)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.core.permissions.IsAuthenticatedBiz",
    ],
    "EXCEPTION_HANDLER": "apps.core.exception_handler.handle",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": None,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.middleware.RequestIdLogFilter"},
    },
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "default",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
