"""申请留存物理清理预留；不按固定期限清理申请或简历。"""
from datetime import datetime


def purge_expired_applications(recruitment_id: int, *, now: datetime | None = None) -> bool:
    """申请留存聚合与物理清理的预留入口。

    Args:
        recruitment_id: 计划清理的招募主键。
        now: 可选业务时间，当前实现不使用。

    Raises:
        NotImplementedError: 当前未实现物理清理，调用始终被拒绝。
    """
    raise NotImplementedError("reserved")
