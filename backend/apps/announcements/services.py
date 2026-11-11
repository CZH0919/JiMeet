"""公告写入函数：每个函数在一个事务内写表并写审计。

权限判断不在此处，在视图层处理：
发布要求管理员；编辑（含置顶）仅发布者；删除为发布者或管理员。
"""
from django.db import transaction

from apps.announcements.models import Announcement
from apps.audit import actions
from apps.audit.service import record
from apps.core.clock import now

EDITABLE_FIELDS = frozenset(
    {"title", "content", "time_kind", "event_at", "link_url", "recruitment", "is_pinned"}
)
TARGET_TYPE = "announcement"


def create_announcement(
    *, author, title, content, time_kind, event_at, link_url=None, recruitment=None
) -> Announcement:
    """创建公告并记录 announcement_publish 审计。

    Args:
        author: 发布者（管理员）。
        title: 竞赛或活动名称。
        content: 公告正文。
        time_kind: deadline 或 event。
        event_at: 与 time_kind 对应的时间。
        link_url: 可空的相关网站。
        recruitment: 可空的关联招募对象。

    Returns:
        Announcement: 新建的公告。
    """
    with transaction.atomic():
        announcement = Announcement.objects.create(
            author=author,
            title=title,
            content=content,
            time_kind=time_kind,
            event_at=event_at,
            link_url=link_url,
            recruitment=recruitment,
        )
        record(
            actor=author,
            action=actions.ANNOUNCEMENT_PUBLISH,
            target_type=TARGET_TYPE,
            target_id=announcement.pk,
        )
    return announcement


def update_announcement(announcement: Announcement, *, actor, **fields) -> Announcement:
    """更新公告内容并记录 announcement_update 审计。

    Args:
        announcement: 待更新的公告。
        actor: 操作者。
        **fields: 仅允许 title、content、time_kind、event_at、link_url、recruitment、is_pinned。

    Returns:
        Announcement: 更新后的公告。

    Raises:
        ValueError: 包含不允许修改的字段。
    """
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"不允许修改的字段: {sorted(unknown)}")
    with transaction.atomic():
        for name, value in fields.items():
            setattr(announcement, name, value)
        announcement.save(update_fields=[*fields, "updated_at"])
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_UPDATE,
            target_type=TARGET_TYPE,
            target_id=announcement.pk,
        )
    return announcement

def soft_delete_announcement(
    announcement: Announcement, *, actor, reason=None
) -> Announcement:
    """软删除公告并记录 announcement_delete 审计，理由可选。

    Args:
        announcement: 待删除的公告。
        actor: 操作者。
        reason: 可空的删除理由，写入审计。

    Returns:
        Announcement: 已设置 deleted_at 的公告。
    """
    with transaction.atomic():
        announcement.deleted_at = now()
        announcement.save(update_fields=["deleted_at", "updated_at"])
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_DELETE,
            target_type=TARGET_TYPE,
            target_id=announcement.pk,
            reason=reason,
        )
    return announcement
