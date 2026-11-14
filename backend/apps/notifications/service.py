"""在业务事务内创建站内通知。

Sprint2 起业务事件只生成站内通知：不再创建 EmailLog(PENDING)，也不再挂接
邮件派发回调；`email_notify_enabled` 与 email_log 表保留为兼容数据，不控制发信。
"""
from apps.core.tx import assert_in_atomic
from apps.notifications import templates, types
from apps.notifications.models import Notification


def notify(
    *, recipient, type: str, recruitment=None, application=None, announcement=None,
    context: dict | None = None,
) -> Notification:
    """在业务事务内创建一条站内通知。

    关联规则：申请事件必须同时关联申请与招聘；公告治理通知只关联公告，
    与招聘/申请关联互斥。按事件校验接收人，不按固定期限抑制通知。
    同一事件的幂等由业务服务在对象锁和状态校验下保证。

    Args:
        recipient: 已保存的接收用户；不在此处执行会话认证。
        type: apps.notifications.types 中的通知类型常量。
        recruitment: 可选关联招聘；要求关联的类型必须提供，默认 None。
        application: 可选关联申请；申请事件及部分招募通知必须提供，默认 None。
        announcement: 可选关联公告；仅公告治理通知提供，与其他关联互斥，默认 None。
        context: 可选的模板摘要字段，仅接受 templates 声明的键。

    Returns:
        Notification: 新创建的通知，随调用方业务事务提交或回滚。

    Raises:
        RuntimeError: 未处于业务事务内。
        ValueError: 通知类型、关联关系、接收人、治理原因或模板上下文字段不合法。
    """
    assert_in_atomic()
    if type not in types.ALL:
        raise ValueError("未知通知类型")
    if type in types.ANNOUNCEMENT_EVENTS:
        if announcement is None or recruitment is not None or application is not None:
            raise ValueError("公告通知必须只关联公告")
        expected_recipient = announcement.author_id
    elif announcement is not None:
        raise ValueError("该通知不能关联公告")
    elif type in types.REQUIRES_APPLICATION:
        if application is None or recruitment is None:
            raise ValueError("该通知必须同时关联申请与招聘")
        if application.recruitment_id != recruitment.pk:
            raise ValueError("申请与招聘不匹配")
        expected_recipient = (
            recruitment.publisher_id if type in types.PUBLISHER_APPLICATION_EVENTS else application.applicant_id
        )
    else:
        if recruitment is None or application is not None:
            raise ValueError("该通知必须只关联招聘")
        expected_recipient = recruitment.publisher_id
    if recipient.pk != expected_recipient:
        raise ValueError("通知接收人与业务事件不匹配")
    values = dict(context or {})
    if type in {types.ADMIN_REMOVED, types.ANNOUNCEMENT_ADMIN_REMOVED}:
        reason = values.get("reason_label")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("治理通知必须包含处置原因")
    if recruitment is not None:
        values["recruitment_title"] = recruitment.title
    if announcement is not None:
        values["announcement_title"] = announcement.title
    title, content = templates.render(type, values)
    return Notification.objects.create(
        recipient=recipient, type=type, recruitment=recruitment,
        application=application, announcement=announcement,
        title=title, content=content,
    )
