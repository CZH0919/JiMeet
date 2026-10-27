"""通知的显式已读操作；通知仅能由接收者修改。"""

from django.db import transaction

from apps.core.errors import NotFound
from apps.notifications.selectors import list_notifications, visible_notifications


def mark_notification_read(*, user, notification_id: int, now):
    with transaction.atomic():
        notification = (
            visible_notifications(user, now)
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


def mark_all_notifications_read(*, user, now) -> int:
    with transaction.atomic():
        return list_notifications(user=user, now=now, is_read=False).update(is_read=True)
