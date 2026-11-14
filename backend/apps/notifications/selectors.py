"""通知的接收人及目标关联权限过滤，不按固定期限隐藏历史。"""

from django.db.models import F, Q
from apps.notifications.models import Notification


def visible_notifications(user):
    """查询当前用户仍可见的站内通知。

    Args:
        user: 已认证的通知接收者。

    Returns:
        QuerySet[Notification]: 仅含本人且关联关系合法的记录，按时间和主键倒序并预加载目标。
    """
    related_application = (
        Q(application__isnull=False)
        & Q(recruitment_id=F("application__recruitment_id"))
        & (Q(application__applicant_id=user.pk) | Q(application__recruitment__publisher_id=user.pk))
    )
    related_recruitment = Q(
        application__isnull=True,
        recruitment__isnull=False,
        recruitment__publisher_id=user.pk,
    )
    related_announcement = Q(announcement__author_id=user.pk, application__isnull=True, recruitment__isnull=True)
    unassociated = Q(
        application__isnull=True, recruitment__isnull=True, announcement__isnull=True
    )

    return (
        Notification.objects.filter(recipient=user)
        .filter(related_application | related_recruitment | related_announcement | unassociated)
        .select_related("recruitment", "application", "announcement")
        .order_by("-created_at", "-pk")
    )


def list_notifications(*, user, is_read=None):
    """按已读状态筛选本人当前可见通知。

    Args:
        user: 已认证接收者。
        is_read: 可选 bool；默认 None 表示不按已读状态过滤。

    Returns:
        QuerySet[Notification]: 已完成可见性过滤的有序查询集，读取不改变已读标记。
    """
    queryset = visible_notifications(user)
    if is_read is not None:
        queryset = queryset.filter(is_read=is_read)
    return queryset
