#!/usr/bin/env python
"""Django 命令行入口。"""
import os
import sys


def main():
    """
    根据命令行参数选择默认配置，并执行 Django 管理命令。

    从 sys.argv 读取命令及参数；test 命令默认使用 config.settings.test，
    其他命令默认使用 config.settings.dev。已设置的 DJANGO_SETTINGS_MODULE
    保持优先，命令行的 --settings 参数由 Django 处理。

    Raises:
        ImportError: 无法导入 Django，需检查虚拟环境和依赖安装情况
    """
    is_test = len(sys.argv) > 1 and sys.argv[1] == "test"
    default_settings = "config.settings.test" if is_test else "config.settings.dev"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "无法导入 Django。请确认已激活 backend/.venv，"
            "并已安装 requirements/base.txt 中的依赖。"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
