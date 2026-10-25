"""统一时间源。测试用 freeze() 冻结，业务代码一律走 now()。"""
from contextlib import contextmanager
from datetime import datetime

from django.utils import timezone

_frozen: datetime | None = None


def now() -> datetime:
    """
    返回当前时间，若 freeze() 冻结则返回冻结时间。  

    Returns:
        当前时间或冻结时间
    """
    if _frozen is not None:
        return _frozen
    return timezone.now()


@contextmanager
def freeze(moment: datetime):
    """
    冻结时间源，返回上下文管理器。测试用。
    通过 with freeze(moment): ... 使用，退出时恢复之前的时间源。

    Args:
        moment: 冻结的时间点
    Yields:
        冻结的时间点
    """
    global _frozen
    previous = _frozen
    _frozen = moment
    try:
        yield moment
    finally:
        _frozen = previous
