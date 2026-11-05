"""在业务事务内创建站内通知及邮件待发送记录。"""
from django.db import transaction

from apps.core import clock
from apps.core.choices import EmailStatus
from apps.core.tx import assert_in_atomic
from apps.notifications import mail, templates, types
from apps.notifications.models import EmailLog, Notification
from apps.recruitments import rules


def notify(*, recipient, type: str, recruitment, application=None, context: dict | None = None) -> Notification | None:
    """在业务事务内创建站内通知及可选待发邮件记录。

    邮件开关开启时创建 pending 记录；提交后 dispatch 异常仅记日志，真实邮件投递仍预留。

    Args:
        recipient: 已保存的接收用户，读取其邮件通知偏好；不在此处执行会话认证。
        type: apps.notifications.types 中的通知类型常量。
        recruitment: 关联招募；仅不要求关联的类型可为 None。
        application: 可选关联申请；申请事件及部分招募通知必须提供，默认 None。
        context: 可选的模板摘要字段，仅接受 templates 声明的键。

    Returns:
        Notification | None: 新通知；关联申请的通知在留存到期时不生成并返回 None。

    Raises:
        RuntimeError: 未处于业务事务内。
        ValueError: 通知类型、关联关系或模板上下文字段不合法。
    """
    assert_in_atomic()
    if type not in types.ALL:
        raise ValueError("未知通知类型")
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
    values.update(context or {})
    title, content = templates.render(type, values)
    if (type in types.APPLICATION_EVENTS or application is not None) and rules.is_retention_expired(recruitment, clock.now()):
        return None
    notification = Notification.objects.create(
        recipient=recipient, type=type, recruitment=recruitment,
        application=application, title=title, content=content,
    )
    if recipient.email_notify_enabled:
        log = EmailLog.objects.create(
            notification=notification, to_email=recipient.email,
            status=EmailStatus.PENDING, attempts=0,
        )
        # 派发失败不得影响已提交业务，避免异常清理路径删除仍被引用的简历。
        transaction.on_commit(lambda log_id=log.pk: mail.dispatch(log_id), robust=True)
    return notification
