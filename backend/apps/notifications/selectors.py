"""通知列表的当前用户、关联权限及留存期过滤。"""

from datetime import timedelta

from django.db.models import Case, DateTimeField, F, Q, When
from django.db.models.functions import Coalesce, Least

from apps.core.choices import RecruitmentStatus
from apps.notifications.models import Notification


def visible_notifications(user, now):
    """通知只对接收者可见，关联对象须属于当前用户且仍在留存期内。"""
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
    queryset = visible_notifications(user, now)
    if is_read is not None:
        queryset = queryset.filter(is_read=is_read)
    return queryset
