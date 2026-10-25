"""招聘状态流转；补执行与业务操作使用两个独立事务。"""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, TypeVar

from django.db import transaction

from apps.applications.models import Application
from apps.core import clock, tx
from apps.core.choices import ApplicationStatus, CloseReason, PublisherMark, RecruitmentStatus
from apps.notifications import types
from apps.notifications.service import notify
from apps.recruitments import rules
from apps.recruitments.models import Recruitment

T = TypeVar("T")


@dataclass(frozen=True)
class SyncResult:
    """本次补执行发生的关闭、自动拒绝及满员结果。"""

    closed: bool
    auto_rejected: int
    became_full: bool


def reject_processing_applications(recruitment, decided_at: datetime, reason: str) -> int:
    """
    在招聘锁保护下拒绝仍在处理的申请，并在同一事务内创建通知。

    Args:
        recruitment: 招聘对象，必须已加锁。
        decided_at: 拒绝时间。
        reason: 自动拒绝原因，必须是 "closed_timeout" 或 "full"。
    Returns:
        拒绝的申请数量。
    """
    tx.assert_recruitment_locked(recruitment)
    labels = {"closed_timeout": "招聘关闭后的七天处理期已结束", "full": "招聘已满员"}
    if reason not in labels:
        raise ValueError("未知自动拒绝原因")
    # 固定申请加锁顺序；不锁 select_related 的用户行，避免引入额外锁依赖。
    applications = list(Application.objects.select_for_update().filter(
        recruitment=recruitment, status=ApplicationStatus.PROCESSING,
    ).order_by("pk"))
    ids = [application.pk for application in applications]
    Application.objects.filter(pk__in=ids).update(
        status=ApplicationStatus.REJECTED, decided_at=decided_at,
        publisher_mark=PublisherMark.NONE, has_unseen_update=False, updated_at=clock.now(),
    )
    for application in applications:
        notify(
            recipient=application.applicant, type=types.APPLICATION_REJECTED,
            recruitment=recruitment, application=application,
            context={"auto": True, "reason_label": labels[reason]},
        )
    return len(applications)


def sync_recruitment(recruitment_id: int, *, now: datetime | None = None) -> SyncResult:
    """
    实现提交到期关闭及七天自动拒绝；重复调用不重复生成通知。

    Args:
        recruitment_id: 招聘对象的数据库主键
        now: 当前时间，默认为 clock.now()

    Returns:
        SyncResult，表示本次补执行发生的关闭、自动拒绝及满员结果。
    
    """
    tx.assert_not_in_atomic()  # 需要确定在事务外提交补执行，避免锁住业务事务。
    now = now if now is not None else clock.now()
    with tx.recruitment_lock_scope(), transaction.atomic():
        r = tx.lock_recruitment(recruitment_id)
        # 删除时已有独立失效流程，补执行不再改变删除招聘。
        if r.deleted_at is not None:
            return SyncResult(False, 0, False)
        closed = False
        rejected = 0
        if r.status == RecruitmentStatus.OPEN and now >= r.deadline:
            # 若招聘开放，但是时间已过截止，则补执行关闭招聘并拒绝仍在处理的申请。
            r.status = RecruitmentStatus.CLOSED
            r.closed_at = r.deadline
            r.close_reason = CloseReason.DEADLINE
            r.save(update_fields=["status", "closed_at", "close_reason", "updated_at"])
            notify(recipient=r.publisher, type=types.RECRUITMENT_CLOSED, recruitment=r)
            closed = True
        end = rules.seven_day_deadline(r)
        # 两个判断独立执行，任务延迟时可一次补齐关闭与拒绝。
        if r.status == RecruitmentStatus.CLOSED and end is not None and now >= end:
            rejected = reject_processing_applications(r, end, "closed_timeout")
        return SyncResult(closed, rejected, False)


def mark_full(r: Recruitment, now: datetime) -> None:
    """
    在招聘锁内保存满员并拒绝其余申请，保留首次关闭与满员时间。

    调用方先在 r 上增加 accepted_count，达到上限后直接调用本函数；
    不可提前单独保存满员人数，否则会违反 recruitment_full_chk。

    Args:
        r: 招聘对象，必须已加锁。
        now: 当前时间，默认为 clock.now()
    Returns:
        None
    Raises:
        ValueError: 招聘未达到满员条件  
    """
    tx.assert_recruitment_locked(r)
    if r.accepted_count < r.max_headcount:
        raise ValueError("接受人数尚未达到人数上限")
    # 截止后的接受仍可在七天窗口内发生，补记截止时间而不覆盖 full。
    if r.status == RecruitmentStatus.OPEN and now >= r.deadline and r.closed_at is None:
        r.closed_at = r.deadline
        r.close_reason = CloseReason.DEADLINE
    r.status = RecruitmentStatus.FULL
    r.full_at = r.full_at if r.full_at is not None else now
    r.save(update_fields=[
        "accepted_count", "status", "full_at", "closed_at", "close_reason", "updated_at",
    ])
    reject_processing_applications(r, r.full_at, "full")


def run_in_recruitment_tx(recruitment_id: int, fn: Callable[[Recruitment, datetime], T]) -> T:
    """
    先提交补执行，再加锁调用业务回调；回调异常只回滚业务事务。

    Args:
        recruitment_id: 招聘对象的数据库主键
        fn: 业务回调，参数为 (Recruitment, now)，返回值类型为 T
    Returns:
        fn 的返回值
    """
    tx.assert_not_in_atomic() # 依然需要在事务外提交补执行，避免锁住业务事务。
    now = clock.now()
    # sync 首次锁行即检查存在性，不存在时不会产生补执行写入。
    sync_recruitment(recruitment_id, now=now)
    with tx.recruitment_lock_scope(), transaction.atomic():
        r = tx.lock_recruitment(recruitment_id)
        return fn(r, now)
