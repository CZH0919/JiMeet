from contextlib import contextmanager
from threading import local

from django.db import connection

from apps.core.errors import NotFound

_LOCKED_FLAG = "_tx_locked"
_held = local()


def held_recruitment_id() -> int | None:
    """
    返回当前事务持有的招聘锁；事务结束或回滚到加锁前则返回 None。

    Returns:
        招聘对象的数据库主键，或 None
    """
    block = getattr(_held, "atomic_block", None)
    # 记录 atomic 对象身份，防止上一笔事务或已回滚 savepoint 的标记被复用。
    if not connection.in_atomic_block or not any(block is item for item in connection.atomic_blocks):
        return None
    return getattr(_held, "recruitment_id", None)


@contextmanager
def recruitment_lock_scope():
    """
    隔离服务事务的锁标记，退出时无论成功或失败均恢复外层记录。

    ### Usage:
        with tx.recruitment_lock_scope():
            r = tx.lock_recruitment(recruitment_id)
            ...
    
    """
    previous = (_held.__dict__).copy()
    _held.__dict__.clear()
    try:
        yield
    finally:
        _held.__dict__.clear()
        _held.__dict__.update(previous)


def assert_recruitment_locked(recruitment) -> None:
    """
    确认对象在当前事务中已通过 lock_recruitment 加锁。

    Args:
        recruitment: 招聘对象
    
    Raises:
        RuntimeError: 招聘对象未加锁或不属于当前事务
    """
    assert_in_atomic()
    # 同时核对事务和对象标记，拒绝跨事务复用旧对象。
    if (
        held_recruitment_id() != recruitment.pk
        or getattr(recruitment, _LOCKED_FLAG, None) is not getattr(_held, "atomic_block", None)
    ):
        raise RuntimeError("必须先调用 lock_recruitment 持有招聘锁")



def assert_not_in_atomic() -> None:
    """
    检查 service 入口未嵌套在调用方的外层事务中。

    Raises:
        RuntimeError: 当前数据库连接已经处于事务中
    """
    if connection.in_atomic_block:
        raise RuntimeError("该操作不能在事务中执行")


def assert_in_atomic() -> None:
    """
    检查当前数据库连接处于事务中，供行锁操作调用前校验。

    Raises:
        RuntimeError: 当前数据库连接不在事务中
    """
    if not connection.in_atomic_block:
        raise RuntimeError("该操作必须在事务中执行")


def lock_recruitment(recruitment_id: int):
    """
    获取招聘对象并锁住对应数据行，必须在事务内调用。

    Params:
        recruitment_id: 招聘记录的数据库主键

    Returns:
        带有已加锁标记的招聘对象，行锁持续到当前事务结束

    Raises:
        RuntimeError: 当前数据库连接不在事务中
        NotFound: 招聘记录不存在
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
    """
    锁住申请行，并校验申请属于已加锁的招聘。

    Params:
        application_id: 申请记录的数据库主键
        recruitment: 在当前事务中通过 lock_recruitment 获取的招聘对象

    Returns:
        属于指定招聘的申请对象，行锁持续到当前事务结束

    Raises:
        RuntimeError: 不在事务中、招聘缺少已加锁标记，或申请不属于该招聘
        NotFound: 申请记录不存在
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
    """
    只读查询申请所属的招聘主键，供后续按招聘、申请的顺序加锁。

    此查询不加锁，不能依据此次读取的状态作业务决定。

    Params:
        application_id: 申请记录的数据库主键

    Returns:
        申请所属招聘的数据库主键

    Raises:
        NotFound: 申请记录不存在
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
