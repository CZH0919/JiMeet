"""通知列表的当前用户、关联权限及留存期过滤。"""

from datetime import timedelta

from django.db.models import Case, DateTimeField, F, Q, When
from django.db.models.functions import Coalesce, Least

from apps.core.choices import RecruitmentStatus
from apps.notifications.models import Notification


def visible_notifications(user, now):
    """查询当前用户仍可见的站内通知。

    Args:
        user: 已认证的通知接收者。
        now: 用于留存期限和招募截止投影的时间点。

    Returns:
        QuerySet[Notification]: 按时间和主键倒序，过滤关联关系不符及留存到期记录，预加载关联对象。
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
    unassociated = Q(application__isnull=True, recruitment__isnull=True)

    return (
        Notification.objects.filter(recipient=user)
        .filter(related_application | related_recruitment | unassociated)
        .alias(
            effective_closed_at=Case(
                When(
                    recruitment__status=RecruitmentStatus.OPEN,
                    recruitment__deadline__lte=now,
                    then=Coalesce("recruitment__closed_at", "recruitment__deadline"),
                ),
                default=F("recruitment__closed_at"),
                output_field=DateTimeField(),
            ),
        )
        .alias(
            retention_start=Least(
                "effective_closed_at", "recruitment__full_at", "recruitment__deleted_at",
            ),
        )
        .filter(
            Q(recruitment__isnull=True)
            | Q(retention_start__isnull=True)
            | Q(retention_start__gt=now - timedelta(days=180))
        )
        .select_related("recruitment", "application")
        .order_by("-created_at", "-pk")
    )


def list_notifications(*, user, now, is_read=None):
    """按已读状态筛选本人当前可见通知。

    Args:
        user: 已认证接收者。
        now: 留存及时间状态判断时点。
        is_read: 可选 bool；默认 None 表示不按已读状态过滤。

    Returns:
        QuerySet[Notification]: 已完成可见性过滤的有序查询集，读取不改变已读标记。
    """
    queryset = visible_notifications(user, now)
    if is_read is not None:
        queryset = queryset.filter(is_read=is_read)
    return queryset
