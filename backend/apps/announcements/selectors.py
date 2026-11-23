"""公告与投稿只读查询；权限由视图层判断。"""
from datetime import timedelta

from django.db.models import BooleanField, Case, Value, When

from apps.announcements.models import Announcement, AnnouncementSubmission
from apps.core.clock import now

OVERDUE_AFTER = timedelta(hours=24)


def list_announcements():
    """查询未删除的公告。

    Returns:
        QuerySet[Announcement]: 按发布时间、主键倒序稳定排序（HTTP 不按置顶排序），
            预加载作者与关联招募。
    """
    return (
        Announcement.objects.filter(deleted_at__isnull=True)
        .select_related("author", "recruitment")
        .order_by("-created_at", "-id")
    )


def get_announcement(announcement_id: int):
    """读取单条未删除的公告。

    Args:
        announcement_id: 公告主键。

    Returns:
        Announcement | None: 不存在或已删除时为 None。
    """
    return list_announcements().filter(pk=announcement_id).first()


def list_my_submissions(user):
    """查询本人投稿（含全部状态），按提交时间倒序。

    Args:
        user: 当前用户。

    Returns:
        QuerySet[AnnouncementSubmission]: 预加载审核人与生成公告。
    """
    return (
        AnnouncementSubmission.objects.filter(submitter=user)
        .select_related("reviewed_by", "announcement")
        .order_by("-submitted_at", "-id")
    )


def list_pending_submissions():
    """查询共享待审池：仅待审投稿，逾期（超 24 小时未处理）优先。

    组内按提交时间、编号升序；返回的 `overdue` 为逾期标记。

    Returns:
        QuerySet[AnnouncementSubmission]: 预加载投稿人与领取人，含 overdue 注解。
    """
    cutoff = now() - OVERDUE_AFTER
    return (
        AnnouncementSubmission.objects.filter(status=AnnouncementSubmission.STATUS_PENDING)
        .select_related("submitter", "claimed_by")
        .annotate(
            overdue=Case(
                When(submitted_at__lt=cutoff, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        .order_by("-overdue", "submitted_at", "id")
    )
