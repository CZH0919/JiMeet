"""招聘时间与人数规则；只读取传入对象，不查询数据库。"""
from datetime import datetime, timedelta

from django.conf import settings

from apps.core.choices import RecruitmentStatus
from apps.core.errors import ValidationFailed


def add_one_year(dt: datetime) -> datetime:
    """按日历增加一年，闰日回退至次年二月末。

    Args:
        dt: 需要增加一年的 datetime，保留其时区。

    Returns:
        datetime: 增加一个日历年的时间。
    """
    try:
        return dt.replace(year=dt.year + 1)
    except ValueError:
        return dt.replace(year=dt.year + 1, day=28)


def validate_deadline(deadline: datetime, now: datetime) -> None:
    """校验截止时间严格晚于当前时间，且不超过一个日历年。

    Args:
        deadline: 拟保存的带时区截止时间。
        now: 带时区的业务当前时间。

    Raises:
        ValidationFailed: 截止时间不满足 now < deadline <= add_one_year(now)。
    """
    if not now < deadline <= add_one_year(now):
        raise ValidationFailed(details={"deadline": "截止时间须晚于当前时间且不超过一年"})


def validate_headcount(min_headcount: int | None, max_headcount: int) -> None:
    """校验人数为整数且满足范围约束。

    Args:
        min_headcount: 可选人数下限；None 表示未设置，设置时须为 1 至上限间的整数。
        max_headcount: 人数上限，须为 1 至 MAX_HEADCOUNT_LIMIT 的整数，不接受 bool。

    Raises:
        ValidationFailed: 人数类型、大小或上下限关系不合法。
    """
    if type(max_headcount) is not int or not 1 <= max_headcount <= settings.MAX_HEADCOUNT_LIMIT:
        raise ValidationFailed(details={"max_headcount": f"人数须为 1 至 {settings.MAX_HEADCOUNT_LIMIT} 的整数"})
    if min_headcount is not None and (
        type(min_headcount) is not int or not 1 <= min_headcount <= max_headcount
    ):
        raise ValidationFailed(details={"min_headcount": "最少人数须为正整数且不超过最多人数"})


def seven_day_deadline(r) -> datetime | None:
    """计算首次关闭后的七天处理截止点。

    Args:
        r: 招募对象；调用方应先补执行或投影到期状态。

    Returns:
        datetime | None: closed_at 加七天；未关闭时为 None。
    """
    return r.closed_at + timedelta(days=7) if r.closed_at is not None else None


def is_apply_open(r, now: datetime) -> bool:
    """判断招募是否仍处于投递窗口。

    Args:
        r: 招募对象。
        now: 带时区的业务时间。

    Returns:
        bool: 未删除、状态 open 且 now 严格早于 deadline 时为 True。
    """
    return r.deleted_at is None and r.status == RecruitmentStatus.OPEN and now < r.deadline


def is_processable(r, now: datetime) -> bool:
    """判断招募是否仍允许处理已有申请。

    Args:
        r: 招募对象。
        now: 带时区的业务时间。

    Returns:
        bool: 未删除，且为未截止 open，或尚未到关闭后七天边界的 closed。
    """
    if r.deleted_at is not None:
        return False
    if r.status == RecruitmentStatus.OPEN:
        return now < r.deadline
    end = seven_day_deadline(r)
    return r.status == RecruitmentStatus.CLOSED and end is not None and now < end


def is_editable(r, now: datetime) -> bool:
    """判断招募是否仍允许编辑。

    Args:
        r: 招募对象。
        now: 带时区的业务时间。

    Returns:
        bool: 与开放投递窗口条件一致，不含操作者身份判断。
    """
    return is_apply_open(r, now)


def is_publisher_deletable(r, now: datetime) -> bool:
    """判断发布者删除招募的时间与状态条件。

    Args:
        r: 招募对象。
        now: 带时区的业务时间。

    Returns:
        bool: 与编辑窗口条件一致，身份判断由策略层完成。
    """
    return is_editable(r, now)
