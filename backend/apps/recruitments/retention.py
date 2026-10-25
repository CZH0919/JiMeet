"""申请留存清理预留；本周不删除申请、通知或简历。"""
from datetime import datetime


def purge_expired_applications(recruitment_id: int, *, now: datetime | None = None) -> bool:
    """预留 180 天统计聚合与明细清理入口，后续实现须遵循数据库设计。"""
    raise NotImplementedError("reserved for week 2")
