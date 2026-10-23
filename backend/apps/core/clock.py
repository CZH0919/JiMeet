"""统一时间源。测试用 freeze() 冻结，业务代码一律走 now()。"""
from contextlib import contextmanager
from datetime import datetime

from django.utils import timezone

_frozen: datetime | None = None


def now() -> datetime:
    if _frozen is not None:
        return _frozen
    return timezone.now()


@contextmanager
def freeze(moment: datetime):
    global _frozen
    previous = _frozen
    _frozen = moment
    try:
        yield moment
    finally:
        _frozen = previous
