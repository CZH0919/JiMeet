"""在业务事务内创建站内通知。

Sprint2 起业务事件只生成站内通知：不再创建 EmailLog(PENDING)，也不再挂接
邮件派发回调；`email_notify_enabled` 与 email_log 表保留为兼容数据，不控制发信。
"""
from django.db import transaction

from apps.core import clock
from apps.core.tx import assert_in_atomic
from apps.notifications import templates, types
from apps.notifications.models import Notification
from apps.recruitments import rules


def notify(
    *, recipient, type: str, recruitment=None, application=None, announcement=None,
    context: dict | None = None,
) -> Notification | None:
    """在业务事务内创建一条站内通知。

    关联规则：申请事件必须同时关联申请与招聘；公告治理通知只关联公告，
    与招聘/申请关联互斥；其他类型按既有语义关联招聘或不关联。

    Args:
        recipient: 已保存的接收用户；不在此处执行会话认证。
        type: apps.notifications.types 中的通知类型常量。
        recruitment: 可选关联招聘；要求关联的类型必须提供，默认 None。
        application: 可选关联申请；申请事件及部分招募通知必须提供，默认 None。
        announcement: 可选关联公告；仅公告治理通知提供，与其他关联互斥，默认 None。
        context: 可选的模板摘要字段，仅接受 templates 声明的键。

    Returns:
        Notification | None: 新通知；关联招聘/申请的通知在留存到期时不生成并返回 None。

    Raises:
        RuntimeError: 未处于业务事务内。
        ValueError: 通知类型、关联关系或模板上下文字段不合法。
    """
    assert_in_atomic()
    if type not in types.ALL:
        raise ValueError("未知通知类型")
    if type in types.ANNOUNCEMENT_EVENTS:
        if announcement is None or recruitment is not None or application is not None:
            raise ValueError("公告通知必须只关联公告")
    elif announcement is not None:
        raise ValueError("该通知不能关联公告")
    requires_application = type in types.REQUIRES_APPLICATION or (
        type == types.RECRUITMENT_DELETED
        and (recruitment is None or recipient.pk != recruitment.publisher_id)
    )
    if requires_application and (application is None or recruitment is None):
        raise ValueError("该通知必须同时关联申请与招聘")
    if application is not None and (
        recruitment is None or application.recruitment_id != recruitment.pk
    ):
        raise ValueError("申请与招聘不匹配")
    values = {"recruitment_title": recruitment.title} if recruitment is not None else {}
    if announcement is not None:
        values["announcement_title"] = announcement.title
    values.update(context or {})
    title, content = templates.render(type, values)
    if recruitment is not None and (
        type in types.APPLICATION_EVENTS or application is not None
    ) and rules.is_retention_expired(recruitment, clock.now()):
        return None
    return Notification.objects.create(
        recipient=recipient, type=type, recruitment=recruitment,
        application=application, announcement=announcement,
        title=title, content=content,
    )
