"""Keep test login independent of DEBUG without enabling it in production."""
from django.conf import settings


def development_login_enabled():
    return settings.ALLOW_DEV_LOGIN and (
        settings.DEBUG or getattr(settings, "STAGING_LOGIN_ENABLED", False)
    )
