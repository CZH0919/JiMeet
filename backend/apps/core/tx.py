"""业务事务的前置校验及招募、申请行锁顺序控制。"""
from contextlib import contextmanager
from threading import local

from django.db import connection

from apps.core.errors import NotFound

_LOCKED_FLAG = "_tx_locked"
_held = local()


def held_recruitment_id() -> int | None:
    """读取当前有效事务作用域持有的招募锁标记。

    Returns:
        int | None: 招募主键；事务已退出或对应保存点已回滚时为 None。
    """
    block = getattr(_held, "atomic_block", None)
    # 记录 atomic 对象身份，防止上一笔事务或已回滚 savepoint 的标记被复用。
    if not connection.in_atomic_block or not any(block is item for item in connection.atomic_blocks):
        return None
    return getattr(_held, "recruitment_id", None)


@contextmanager
def recruitment_lock_scope():
    """隔离行锁标记，退出时恢复外层标记。

    本上下文不创建数据库事务，也不主动获取行锁。

    Yields:
        None: 供业务事务在上下文内获取锁。
    """
    previous = (_held.__dict__).copy()
    _held.__dict__.clear()
    try:
        yield
    finally:
        _held.__dict__.clear()
        _held.__dict__.update(previous)


def assert_recruitment_locked(recruitment) -> None:
    """确认招募对象在当前事务中持有有效行锁。

    Args:
        recruitment: 通过 lock_recruitment 获取的招募对象。

    Raises:
        RuntimeError: 不在事务中，或对象/事务的行锁标记不匹配。
    """
    assert_in_atomic()
    # 同时核对事务和对象标记，拒绝跨事务复用旧对象。
    if (
        held_recruitment_id() != recruitment.pk
        or getattr(recruitment, _LOCKED_FLAG, None) is not getattr(_held, "atomic_block", None)
    ):
        raise RuntimeError("必须先调用 lock_recruitment 持有招聘锁")



def assert_not_in_atomic() -> None:
    """要求服务入口不处于调用方的外层事务。

    Raises:
        RuntimeError: 当前连接已处于 atomic 事务中。
    """
    if connection.in_atomic_block:
        raise RuntimeError("该操作不能在事务中执行")


def assert_in_atomic() -> None:
    """要求当前数据库连接已进入事务。

    Raises:
        RuntimeError: 当前连接不在 atomic 事务中。
    """
    if not connection.in_atomic_block:
        raise RuntimeError("该操作必须在事务中执行")


def lock_recruitment(recruitment_id: int):
    """锁定招募行，并记录当前事务的锁标记。

    Args:
        recruitment_id: 招募主键。

    Returns:
        Recruitment: 持有行锁的招募对象，锁持续到事务结束。

    Raises:
        RuntimeError: 调用方未开启事务。
        NotFound: 招募不存在。
    """
    assert_in_atomic()
    from apps.recruitments.models import Recruitment

    try:
        recruitment = Recruitment.objects.select_for_update().get(pk=recruitment_id)
    except Recruitment.DoesNotExist:
        raise NotFound("招聘不存在") from None
    _held.recruitment_id = recruitment.pk
    _held.atomic_block = connection.atomic_blocks[-1]
    setattr(recruitment, _LOCKED_FLAG, _held.atomic_block)
    return recruitment


def lock_application(application_id: int, recruitment):
    """在招募锁之后获取所属申请的行锁。

    Args:
        application_id: 申请主键。
        recruitment: 当前事务中已锁定的招募对象。

    Returns:
        Application: 已加锁且归属匹配的申请对象。

    Raises:
        RuntimeError: 缺少有效招募锁、不在事务中，或申请不属于该招募。
        NotFound: 申请不存在。
    """
    assert_in_atomic()
    assert_recruitment_locked(recruitment)
    from apps.applications.models import Application

    try:
        application = Application.objects.select_for_update().get(pk=application_id)
    except Application.DoesNotExist:
        raise NotFound("申请不存在") from None
    if application.recruitment_id != recruitment.id:
        raise RuntimeError("申请不属于该招聘")
    return application


def peek_application_recruitment_id(application_id: int) -> int:
    """只读查询申请所属招募，供调用方确定加锁顺序。

    不获取行锁；业务状态必须在取得招募锁及申请锁后重新校验。

    Args:
        application_id: 申请主键。

    Returns:
        int: 招募主键。

    Raises:
        NotFound: 申请不存在。
    """
    from apps.applications.models import Application

    recruitment_id = (
        Application.objects.filter(pk=application_id)
        .values_list("recruitment_id", flat=True)
        .first()
    )
    if recruitment_id is None:
        raise NotFound("申请不存在")
    return recruitment_id
