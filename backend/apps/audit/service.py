"""审计追加入口，业务审计应与业务操作在同一事务内调用。"""
from apps.audit import actions
from apps.audit.models import AuditLog


def record(*, actor, action: str, target_type: str, target_id: int | None, reason: str | None = None) -> AuditLog:
    """
    保存操作者身份快照，原因最多保存 500 字。

    只有 permission_denied 允许空操作者；admin_delete 必须给出非空原因。
    调用方不得在 reason 中传入认证凭证、简历内容、原始文件名或申请补充说明。

    Args:
        actor: 操作者，若为 None 则仅允许 action 为 PERMISSION_DENIED
        action: 审计动作，必须是 apps.audit.actions.ALL 中的值
        target_type: 审计对象类型，非空字符串，如 recruitment / application / request
        target_id: 审计对象 ID，可为 None
        reason: 审计原因，最多保存 500 字，可为 None

    Returns:
        新增的审计记录对象

    Raises:
        ValueError: action 未知、target_type 为空、业务审计缺操作者或 admin_delete 缺原因
    """
    if action not in actions.ALL:
        raise ValueError(f"未知审计动作: {action}")
    if not target_type or not target_type.strip():
        raise ValueError("target_type 必填")
    if action == actions.ADMIN_DELETE and not (reason and reason.strip()):
        raise ValueError("管理员删除必须填写原因")
    if actor is None and action != actions.PERMISSION_DENIED:
        raise ValueError("业务审计必须提供操作者")
    return AuditLog.objects.create(
        actor=actor,
        actor_role=actor.role if actor is not None else None,
        actor_is_admin=actor.is_admin if actor is not None else None,
        action=action, target_type=target_type, target_id=target_id,
        reason=reason[:500] if reason is not None else None,
    )
