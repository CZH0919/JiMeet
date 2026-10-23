"""测试配置。"""
import tempfile
from pathlib import Path

from .dev import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

PRIVATE_FILE_ROOT = Path(tempfile.gettempdir()) / "jimeet-test-private"
