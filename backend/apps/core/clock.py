"""统一时间源。测试用 freeze() 冻结，业务代码一律走 now()。"""
from contextlib import contextmanager
from datetime import datetime

from django.utils import timezone

_frozen: datetime | None = None


def now() -> datetime:
    """读取统一业务时钟。

    Returns:
        datetime: freeze 生效时返回指定时间，否则返回 Django 当前时间。
    """
    if _frozen is not None:
        return _frozen
    return timezone.now()


@contextmanager
def freeze(moment: datetime):
    """临时覆盖进程内的业务时钟，并在退出时恢复。

    覆盖值对该进程内调用 now 的代码可见，支持嵌套使用。

    Args:
        moment: 测试使用的时间点，应为带时区的 datetime。

    Yields:
        None: 上下文期间启用指定时间。
    """
    global _frozen
    previous = _frozen
    _frozen = moment
    try:
        yield moment
    finally:
        _frozen = previous
