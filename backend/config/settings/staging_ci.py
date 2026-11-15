"""Regression tests on the shared server use isolated database and file storage."""
from .test import *  # noqa: F401,F403

if DATABASES["default"]["NAME"] != "jimeet_staging_ci":
    raise RuntimeError("Server regression tests require the dedicated CI database")
PRIVATE_FILE_ROOT = Path('/srv/jimeet-staging/shared/ci-private')
