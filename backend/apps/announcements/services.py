"""公告写入函数：每个函数在一个事务内锁行、复核状态与权限，写表并写审计。

视图层做请求入口校验；更新和删除锁定公告行，并在事务内重新读取操作者权限：
发布要求当前管理员；编辑与本人删除同时要求当前管理员与作者身份；
治理删除要求当前管理员与非空原因，并在同一事务内通知公告作者。
重复删除或对已删除对象的更新抛出 NotFound，不重复写审计与通知。
"""
from django.db import transaction

from apps.accounts.models import User
from apps.announcements.models import Announcement
from apps.audit import actions
from apps.audit.service import record
from apps.core.clock import now
from apps.core.errors import Forbidden, NotFound
from apps.notifications import types
from apps.notifications.service import notify

EDITABLE_FIELDS = frozenset(
    {"title", "content", "time_kind", "event_at", "link_url", "recruitment", "is_pinned"}
)
TARGET_TYPE = "announcement"


def _lock_and_check(announcement_id: int, *, actor, require_author: bool):
    """锁定公告行并复核存在性与当前权限。

    Args:
        announcement_id: 公告主键。
        actor: 操作者；在锁内刷新其管理员状态，捕获并发撤权。
        require_author: True 时同时要求操作者为公告作者（编辑、本人删除）。

    Returns:
        Announcement: 已锁定且未删除的公告对象。

    Raises:
        NotFound: 公告不存在或已删除。
        Forbidden: 操作者当前无管理员权限，或要求作者身份时不匹配。
    """
    try:
        locked = Announcement.objects.select_for_update().get(pk=announcement_id)
    except Announcement.DoesNotExist:
        raise NotFound("公告不存在") from None
    if locked.deleted_at is not None:
        raise NotFound("公告不存在")
    refreshed = (
        User.objects.filter(pk=actor.pk).values_list("is_admin", "id").first()
    )
    if refreshed is None or not refreshed[0]:
        raise Forbidden("需要管理员权限")
    if require_author and locked.author_id != actor.pk:
        raise Forbidden("仅公告作者可执行该操作")
    return locked


def create_announcement(
    *, actor, title, content, time_kind, event_at, link_url=None, recruitment=None
) -> Announcement:
    """创建公告并记录 announcement_publish 审计；要求操作者当前为管理员。

    Args:
        actor: 发布者，须为当前管理员（锁外入口校验，写入时复核）。
        title: 竞赛或活动名称。
        content: 公告正文。
        time_kind: deadline 或 event。
        event_at: 与 time_kind 对应的时间。
        link_url: 可空的相关网站。
        recruitment: 可空的关联招募对象。

    Returns:
        Announcement: 新建的公告。

    Raises:
        Forbidden: 操作者当前不具管理员权限。
    """
    with transaction.atomic():
        refreshed = User.objects.filter(pk=actor.pk).values_list("is_admin", flat=True).first()
        if not refreshed:
            raise Forbidden("需要管理员权限")
        announcement = Announcement.objects.create(
            author=actor,
            title=title,
            content=content,
            time_kind=time_kind,
            event_at=event_at,
            link_url=link_url,
            recruitment=recruitment,
        )
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_PUBLISH,
            target_type=TARGET_TYPE,
            target_id=announcement.pk,
        )
    return announcement


def update_announcement(announcement_id: int, *, actor, **fields) -> Announcement:
    """更新公告内容并记录 announcement_update 审计；要求当前管理员且为作者。

    Args:
        announcement_id: 公告主键。
        actor: 操作者。
        **fields: 仅允许 title、content、time_kind、event_at、link_url、recruitment、is_pinned。

    Returns:
        Announcement: 更新后的公告。

    Raises:
        ValueError: 包含不允许修改的字段。
        NotFound: 公告不存在或已删除（含更新/删除竞争中的后到请求）。
        Forbidden: 操作者当前无管理员权限或非作者。
    """
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"不允许修改的字段: {sorted(unknown)}")
    with transaction.atomic():
        locked = _lock_and_check(announcement_id, actor=actor, require_author=True)
        for name, value in fields.items():
            setattr(locked, name, value)
        locked.save(update_fields=[*fields, "updated_at"])
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_UPDATE,
            target_type=TARGET_TYPE,
            target_id=locked.pk,
        )
    return locked


def soft_delete_announcement(announcement_id: int, *, actor) -> Announcement:
    """本人软删除公告并记录 announcement_delete 审计；无原因、无通知。

    Args:
        announcement_id: 公告主键。
        actor: 操作者，须为当前管理员且是公告作者。

    Returns:
        Announcement: 已设置 deleted_at 的公告。

    Raises:
        NotFound: 公告不存在或已删除；重复删除返回同一结果，不重复写审计。
        Forbidden: 操作者当前无管理员权限或非作者。
    """
    with transaction.atomic():
        locked = _lock_and_check(announcement_id, actor=actor, require_author=True)
        locked.deleted_at = now()
        locked.save(update_fields=["deleted_at", "updated_at"])
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_DELETE,
            target_type=TARGET_TYPE,
            target_id=locked.pk,
        )
    return locked


def governance_delete_announcement(announcement_id: int, *, actor, reason: str) -> Announcement:
    """治理删除公告：软删除、审计与作者站内通知在同一事务提交。

    Args:
        announcement_id: 公告主键。
        actor: 操作者，须为当前管理员（允许治理删除本人公告，通知语义一致）。
        reason: 非空处置原因，写入审计并进入通知内容。

    Returns:
        Announcement: 已设置 deleted_at 的公告。

    Raises:
        NotFound: 公告不存在或已删除；重复治理删除不重复写审计与通知。
        Forbidden: 操作者当前无管理员权限。
        ValueError: 原因为空。
    """
    if not (reason and reason.strip()):
        raise ValueError("治理删除必须填写原因")
    with transaction.atomic():
        locked = _lock_and_check(announcement_id, actor=actor, require_author=False)
        locked.deleted_at = now()
        locked.save(update_fields=["deleted_at", "updated_at"])
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_DELETE,
            target_type=TARGET_TYPE,
            target_id=locked.pk,
            reason=reason.strip()[:500],
        )
        notify(
            recipient=locked.author,
            type=types.ANNOUNCEMENT_ADMIN_REMOVED,
            announcement=locked,
            context={"announcement_title": locked.title, "reason_label": reason.strip()[:500]},
        )
    return locked
