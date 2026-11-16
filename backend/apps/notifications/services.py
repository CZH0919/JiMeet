"""通知的显式已读操作；通知仅能由接收者修改。"""

from django.db import transaction

from apps.core.errors import NotFound
from apps.notifications.selectors import list_notifications, visible_notifications


def mark_notification_read(*, user, notification_id: int):
    """将本人可见的一条通知标为已读。

    Args:
        user: 已认证接收者。
        notification_id: 通知主键。

    Returns:
        Notification: 事务提交后的通知对象；重复调用不重复写入。

    Raises:
        NotFound: 通知不存在、不属于本人或已不可见。
    """
    with transaction.atomic():
        notification = (
            visible_notifications(user)
            .select_for_update(of=("self",))
            .filter(pk=notification_id)
            .first()
        )
        if notification is None:
            raise NotFound("通知不存在")
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return notification


def mark_all_notifications_read(*, user) -> int:
    """将本人当前可见的未读通知批量标为已读。

    Args:
        user: 已认证接收者。

    Returns:
        int: 本次实际更新数量；重复调用且无新通知时为 0。
    """
    with transaction.atomic():
        return list_notifications(user=user, is_read=False).update(is_read=True)
