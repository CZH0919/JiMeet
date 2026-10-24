"""在业务事务内创建站内通知及邮件待发送记录。"""
from django.db import transaction

from apps.core import clock
from apps.core.choices import EmailStatus
from apps.core.tx import assert_in_atomic
from apps.notifications import mail, templates, types
from apps.notifications.models import EmailLog, Notification
from apps.recruitments import rules


def notify(*, recipient, type: str, recruitment, application=None, context: dict | None = None) -> Notification | None:
    """
    创建通知，邮件仅在事务提交后交给 dispatch。

    申请事件及发给申请人的招聘通知须同时关联招聘与申请；留存到期
    后不再生成这些通知。context 只允许模板声明的摘要字段。

    Args:
        recipient: 通知接收者，必须是已认证用户
        type: 通知类型，必须是 apps.notifications.types 中定义的常量
        recruitment: 通知关联的招聘对象，可为 None
        application: 通知关联的申请对象，可为 None
        context: 通知模板渲染的摘要字段，只允许 apps.notifications.templates 中声明的摘要字段
    Returns:
        新增的通知对象，若留存到期则返回 None
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
        transaction.on_commit(lambda log_id=log.pk: mail.dispatch(log_id))
    return notification
