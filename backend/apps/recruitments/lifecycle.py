"""申请明细留存边界，供列表、对象权限与清理任务共用。"""
from datetime import timedelta

from django.db.models import Q


RETENTION_PERIOD = timedelta(days=180)


def expired_recruitments(moment, prefix=""):
    """构造到期条件，包含尚未补执行的自然截止及已完成清理的历史招聘。"""
    cutoff = moment - RETENTION_PERIOD
    condition = Q(**{prefix + "applications_anonymized_at__isnull": False})
    for field in ("closed_at", "full_at", "deleted_at"):
        condition |= Q(**{prefix + field + "__lte": cutoff})
    return condition | Q(**{
        prefix + "status": "open", prefix + "closed_at__isnull": True,
        prefix + "deleted_at__isnull": True, prefix + "deadline__lte": cutoff,
    })


def details_expired(recruitment, moment):
    """按首次结束时刻判断申请是否已到清理边界，精确到期即不可读取。"""
    if getattr(recruitment, "applications_anonymized_at", None) is not None:
        return True
    ends = [recruitment.closed_at, recruitment.full_at, recruitment.deleted_at]
    if recruitment.status == "open" and recruitment.closed_at is None and recruitment.deleted_at is None:
        ends.append(recruitment.deadline)
    return any(end is not None and end <= moment - RETENTION_PERIOD for end in ends)
