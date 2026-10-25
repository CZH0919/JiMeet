"""招聘对象权限；管理员权限仅用于删除治理。"""
from dataclasses import dataclass

from apps.recruitments import rules


def _is_publisher(user, r) -> bool:
    return bool(user and user.is_authenticated and user.pk == r.publisher_id)


def can_edit(user, r, now) -> bool:
    """判断操作者是否为可编辑招聘的发布者。"""
    return _is_publisher(user, r) and rules.is_editable(r, now)


def can_close(user, r, now) -> bool:
    """判断发布者能否在截止前手动关闭招聘。"""
    return _is_publisher(user, r) and rules.is_apply_open(r, now)


def can_delete(user, r, now) -> bool:
    """管理员可删除未删除的招聘，发布者受编辑窗口限制。"""
    if not user or not user.is_authenticated or r.deleted_at is not None:
        return False
    return bool(user.is_admin or (_is_publisher(user, r) and rules.is_publisher_deletable(r, now)))


def can_view_applications(user, r) -> bool:
    """仅发布者可以查看该招聘下的申请，管理员身份不增加权限。"""
    return _is_publisher(user, r)


@dataclass(frozen=True)
class PublishView:
    """详情页展示的投递入口状态。"""

    can_apply: bool
    apply_blocked_reason: str | None


def publish_state_for_viewer(user, r, now) -> PublishView:
    """先判断本人招聘，再判断是否处于投递窗口。"""
    if _is_publisher(user, r):
        return PublishView(False, "own")
    if not rules.is_apply_open(r, now):
        return PublishView(False, "not_open")
    return PublishView(True, None)
