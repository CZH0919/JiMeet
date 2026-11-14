"""招聘对象权限；管理员权限仅用于删除治理。"""
from dataclasses import dataclass

from apps.recruitments import rules


def _is_publisher(user, r) -> bool:
    """检查已认证用户是否为指定招募的发布者。

    Args:
        user: 当前用户，可为 None 或匿名用户。
        r: 招募对象。

    Returns:
        bool: 发布者身份是否匹配。
    """
    return bool(user and user.is_authenticated and user.pk == r.publisher_id)


def can_edit(user, r, now) -> bool:
    """判断发布者当前能否编辑招募。

    Args:
        user: 当前用户。
        r: 招募对象。
        now: 带时区的业务时间。

    Returns:
        bool: 发布者身份匹配且招募未删除、开放、未截止时为 True。
    """
    return _is_publisher(user, r) and rules.is_editable(r, now)


def can_close(user, r, now) -> bool:
    """判断发布者当前能否手动关闭招募。

    Args:
        user: 当前用户。
        r: 招募对象。
        now: 带时区的业务时间。

    Returns:
        bool: 发布者身份匹配且处于开放投递窗口时为 True。
    """
    return _is_publisher(user, r) and rules.is_apply_open(r, now)


def can_delete(user, r, now) -> bool:
    """判断当前用户能否软删除招募。

    Args:
        user: 当前用户。
        r: 招募对象。
        now: 带时区的业务时间。

    Returns:
        bool: 仅处于编辑窗口内的发布者可删除，管理员标记不绕过本人操作限制。
    """
    if not user or not user.is_authenticated or r.deleted_at is not None:
        return False
    return _is_publisher(user, r) and rules.is_publisher_deletable(r, now)


def can_govern_delete(user, r) -> bool:
    """判断治理删除入口是否可展示；服务层仍须重新读取管理员权限。

    Args:
        user: 当前用户。
        r: 目标招聘。

    Returns:
        bool: 已认证管理员且招聘未删除时为 True。
    """
    return bool(user and user.is_authenticated and user.is_admin and r.deleted_at is None)


def can_view_applications(user, r) -> bool:
    """检查申请列表的发布者身份条件。

    Args:
        user: 当前用户。
        r: 招募对象。

    Returns:
        bool: 仅已认证发布者为 True，不因固定留存期限隐藏历史申请。
    """
    return _is_publisher(user, r)


@dataclass(frozen=True)
class PublishView:
    """详情页展示的投递入口状态。"""

    can_apply: bool
    apply_blocked_reason: str | None


def publish_state_for_viewer(user, r, now) -> PublishView:
    """生成仅包含本人招募与开放窗口判断的展示状态。

    不检查认证、隐私同意或重复申请，不能替代完整投递权限校验。

    Args:
        user: 当前用户，可未认证。
        r: 招募对象。
        now: 带时区的业务时间。

    Returns:
        PublishView: apply_blocked_reason 为 own、not_open 或 None。
    """
    if _is_publisher(user, r):
        return PublishView(False, "own")
    if not rules.is_apply_open(r, now):
        return PublishView(False, "not_open")
    return PublishView(True, None)
