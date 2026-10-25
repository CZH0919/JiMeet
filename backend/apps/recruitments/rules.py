"""招聘时间与人数规则；只读取传入对象，不查询数据库。"""
from datetime import datetime, timedelta

from django.conf import settings

from apps.core.choices import RecruitmentStatus
from apps.core.errors import ValidationFailed


def add_one_year(dt: datetime) -> datetime:
    """增加一个日历年，闰日回退到下一年的 2 月 28 日。"""
    try:
        return dt.replace(year=dt.year + 1)
    except ValueError:
        return dt.replace(year=dt.year + 1, day=28)


def validate_deadline(deadline: datetime, now: datetime) -> None:
    """校验截止时间严格晚于当前时间，且不超过一个日历年。"""
    if not now < deadline <= add_one_year(now):
        raise ValidationFailed(details={"deadline": "截止时间须晚于当前时间且不超过一年"})


def validate_headcount(min_headcount: int | None, max_headcount: int) -> None:
    """校验人数为整数，并满足配置上限及最小、最大人数关系。"""
    if type(max_headcount) is not int or not 1 <= max_headcount <= settings.MAX_HEADCOUNT_LIMIT:
        raise ValidationFailed(details={"max_headcount": f"人数须为 1 至 {settings.MAX_HEADCOUNT_LIMIT} 的整数"})
    if min_headcount is not None and (
        type(min_headcount) is not int or not 1 <= min_headcount <= max_headcount
    ):
        raise ValidationFailed(details={"min_headcount": "最少人数须为正整数且不超过最多人数"})


def seven_day_deadline(r) -> datetime | None:
    """返回关闭后的七天处理窗口终点，未关闭时返回 None。"""
    return r.closed_at + timedelta(days=7) if r.closed_at is not None else None


def retention_starts_at(r) -> datetime | None:
    """取关闭、满员、删除的最早时间，后续变化不重新起算。"""
    dates = [dt for dt in (r.closed_at, r.full_at, r.deleted_at) if dt is not None]
    return min(dates) if dates else None


def retention_expires_at(r) -> datetime | None:
    """返回申请明细的 180 天留存期限。"""
    start = retention_starts_at(r)
    return start + timedelta(days=180) if start is not None else None


def is_retention_expired(r, now: datetime) -> bool:
    """到达留存终点即视为过期，不依赖清理任务是否执行。"""
    expires = retention_expires_at(r)
    return expires is not None and now >= expires


def is_apply_open(r, now: datetime) -> bool:
    """招聘未删除、开放且未到截止时间时允许投递。"""
    return r.deleted_at is None and r.status == RecruitmentStatus.OPEN and now < r.deadline


def is_processable(r, now: datetime) -> bool:
    """允许截止前处理开放招聘，或在关闭后的七天窗口内处理。"""
    if r.deleted_at is not None:
        return False
    if r.status == RecruitmentStatus.OPEN:
        return now < r.deadline
    end = seven_day_deadline(r)
    return r.status == RecruitmentStatus.CLOSED and end is not None and now < end


def is_editable(r, now: datetime) -> bool:
    """招聘只在开放且未截止、未删除时允许编辑。"""
    return is_apply_open(r, now)


def is_publisher_deletable(r, now: datetime) -> bool:
    """发布者删除招聘的时间与状态限制同编辑。"""
    return is_editable(r, now)
