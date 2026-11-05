"""招聘状态流转；补执行与业务操作使用两个独立事务。"""
from collections.abc import Iterable
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
    """在招募锁内拒绝处理中申请，并写入结果通知。

    Args:
        recruitment: 当前事务已锁定的招募。
        decided_at: 记录的拒绝决定时间。
        reason: 自动拒绝原因，仅允许 closed_timeout 或 full。

    Returns:
        int: 实际拒绝的申请数。

    Raises:
        RuntimeError: 缺少当前事务的招募锁。
        ValueError: reason 不在允许集合。
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
    """独立提交到期关闭及关闭后七天的自动拒绝。

    已删除招募不再变更；重复调用不重复生成状态通知。关闭时间记录为原截止时间。

    Args:
        recruitment_id: 招募主键。
        now: 可选的带时区时间点，默认读取业务时钟。

    Returns:
        SyncResult: 本次是否关闭、自动拒绝数量；该函数的 became_full 始终为 False。

    Raises:
        NotFound: 招募不存在。
        RuntimeError: 调用方已在事务内。
    """
    tx.assert_not_in_atomic()
    now = now if now is not None else clock.now()
    with tx.recruitment_lock_scope(), transaction.atomic():
        r = tx.lock_recruitment(recruitment_id)
        # 删除时已有独立失效流程，补执行不再改变删除招聘。
        if r.deleted_at is not None:
            return SyncResult(False, 0, False)
        closed = False
        rejected = 0
        if r.status == RecruitmentStatus.OPEN and now >= r.deadline:
            # 关闭时间取实际截止时间，七天处理窗口不因任务延迟而延长。
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


def mark_full(r: Recruitment, now: datetime, *, extra_update_fields: Iterable[str] = ()) -> None:
    """保存满员状态，并拒绝该招募其余处理中申请。

    调用方先修改内存中的人数再调用，不得提前单独保存以免违反满员约束；已有首次关闭/满员时间不被重置。

    Args:
        r: 当前事务已锁定且 accepted_count 已达到 max_headcount 的招募对象。
        now: 本次业务操作的带时区时间，必须显式提供。
        extra_update_fields: 与满员状态同次保存的其他字段名，默认空序列。

    Raises:
        RuntimeError: 缺少当前事务的有效招募锁。
        ValueError: accepted_count 仍小于人数上限。
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
    r.save(update_fields=list(dict.fromkeys([
        *extra_update_fields,
        "accepted_count", "status", "full_at", "closed_at", "close_reason", "updated_at",
    ])))
    reject_processing_applications(r, r.full_at, "full")


def run_in_recruitment_tx(recruitment_id: int, fn: Callable[[Recruitment, datetime], T]) -> T:
    """先提交状态补执行，再在独立事务中执行业务回调。

    回调异常原样传播并回滚业务事务，不撤销已提交的到期补执行；回调中的申请锁必须在招募锁之后取得。

    Args:
        recruitment_id: 招募主键。
        fn: 接收 (已锁定招募, 本次业务时间) 的可调用对象。

    Returns:
        T: 回调的返回值，返回前业务事务已提交。

    Raises:
        NotFound: 招募不存在。
        RuntimeError: 调用方已在事务内。
    """
    tx.assert_not_in_atomic()
    now = clock.now()
    # sync 首次锁行即检查存在性，不存在时不会产生补执行写入。
    sync_recruitment(recruitment_id, now=now)
    with tx.recruitment_lock_scope(), transaction.atomic():
        r = tx.lock_recruitment(recruitment_id)
        return fn(r, now)
