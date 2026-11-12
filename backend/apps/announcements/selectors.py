"""公告只读查询；只返回未软删除的公告，权限由视图层判断。"""
from apps.announcements.models import Announcement


def list_announcements():
    """查询未删除的公告。

    Returns:
        QuerySet[Announcement]: 置顶优先，再按发布时间、主键倒序，预加载作者与关联招募。
    """
    return (
        Announcement.objects.filter(deleted_at__isnull=True)
        .select_related("author", "recruitment")
        .order_by("-is_pinned", "-created_at", "-id")
    )


def get_announcement(announcement_id: int):
    """读取单条未删除的公告。

    Args:
        announcement_id: 公告主键。

    Returns:
        Announcement | None: 不存在或已删除时为 None。
    """
    return list_announcements().filter(pk=announcement_id).first()
