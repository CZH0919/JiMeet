"""测试配置。"""
import getpass
import tempfile
from pathlib import Path

from .dev import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# 按系统用户名隔离，避免同一主机上多个开发账号的测试私有目录互相覆盖或因残留权限失败。
PRIVATE_FILE_ROOT = Path(tempfile.gettempdir()) / f"jimeet-test-private-{getpass.getuser()}"
