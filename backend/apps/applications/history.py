"""在招聘业务事务内追加申请状态变更，不补造历史事件。"""
from datetime import datetime

from apps.applications.models import ApplicationStatusHistory
from apps.core import tx


def record_status_changes(recruitment, applications, *, to_status: str, reason: str,
                          occurred_at: datetime, actor=None) -> int:
    """依据变更前的申请快照写入状态历史，与状态及通知同事务提交。

    Args:
        recruitment: 当前事务已锁定的招聘。
        applications: 已按主键顺序加锁、尚未修改状态的申请对象序列。
        to_status: 目标申请状态。
        reason: ApplicationHistoryReason 中的原因值。
        occurred_at: 业务生效时间；自动补执行采用实际边界时刻。
        actor: 人工操作者；系统自动处理传 None。

    Returns:
        int: 新增变更记录数。

    Raises:
        RuntimeError: 未持有招聘事务锁。
        ValueError: 申请与招聘不匹配，或状态未变化。
        IntegrityError: 状态组合、事件来源或重复变更违反数据库约束。
    """
    tx.assert_recruitment_locked(recruitment)
    rows = []
    for application in applications:
        if application.recruitment_id != recruitment.pk or application.status == to_status:
            raise ValueError("申请状态变更与当前招聘或原状态不符")
        rows.append(ApplicationStatusHistory(
            application=application, recruitment=recruitment,
            from_status=application.status, to_status=to_status,
            reason=reason, actor=actor, occurred_at=occurred_at,
        ))
    ApplicationStatusHistory.objects.bulk_create(rows)
    return len(rows)
