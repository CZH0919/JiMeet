"""招募写服务：权限复核、事务、关联申请、通知与删除审计。"""

from django.db import transaction

from apps.accounts.models import User
from apps.applications.history import record_status_changes
from apps.applications.models import Application, ApplicationHistoryReason
from apps.audit import actions
from apps.audit.service import record
from apps.core import clock, tx
from apps.core.choices import ApplicationStatus, CloseReason, PublisherMark, RecruitmentStatus
from apps.core.errors import Conflict, ErrorCode, Forbidden, NotAuthenticated, NotFound, ValidationFailed
from apps.notifications import types
from apps.notifications.service import notify
from apps.recruitments import policies, rules, state
from apps.recruitments.models import Recruitment, RecruitmentTag, Tag

CONTENT_FIELDS = ("title", "type", "description", "min_headcount", "max_headcount", "deadline")
ACTIVE_APPLICATION_STATUSES = (ApplicationStatus.PROCESSING, ApplicationStatus.ACCEPTED)


def _require_user(user):
    """要求操作者具有已认证身份。

    Args:
        user: 当前操作者，可为 None 或匿名用户。

    Raises:
        NotAuthenticated: 用户未认证。
    """
    if not user or not user.is_authenticated:
        raise NotAuthenticated()


def _authorize(user, recruitment, *, allow_admin=False):
    """检查招募未删除及操作者的对象权限。

    Args:
        user: 已认证操作者。
        recruitment: 待操作招募。
        allow_admin: True 表示治理入口并要求当前管理员；False 表示本人入口。

    Raises:
        NotFound: 招募已删除。
        Forbidden: 不满足所选入口的当前身份条件。
    """
    if recruitment.deleted_at is not None:
        raise NotFound("招募不存在")
    if allow_admin:
        if not User.objects.filter(pk=user.pk, is_admin=True, is_active=True).exists():
            raise Forbidden("需要管理员权限", audit_target=("recruitment", recruitment.pk))
    elif user.pk != recruitment.publisher_id:
        raise Forbidden(audit_target=("recruitment", recruitment.pk))


def _preflight(user, recruitment_id, *, allow_admin=False):
    """在状态补执行前拒绝无权操作者，不获取行锁。

    业务事务获取招募锁后仍须重新检查对象权限。

    Args:
        user: 当前操作者。
        recruitment_id: 招募主键。
        allow_admin: True 使用治理权限，False 仅允许发布者。

    Raises:
        BizError: 未认证、招募不存在或已删除，或对象权限不足。
    """
    _require_user(user)
    try:
        recruitment = Recruitment.objects.only("id", "publisher_id", "deleted_at").get(pk=recruitment_id)
    except Recruitment.DoesNotExist:
        raise NotFound("招募不存在") from None
    _authorize(user, recruitment, allow_admin=allow_admin)


def _active_tags(tag_ids):
    """在当前事务内按主键顺序锁定启用标签。

    Args:
        tag_ids: 非空、去重的标签主键序列。

    Returns:
        list[Tag]: 已锁定的启用标签。

    Raises:
        ValidationFailed: 列表为空、含重复值，或含不存在/停用标签。
    """
    tags = list(Tag.objects.select_for_update().filter(pk__in=tag_ids, is_active=True).order_by("pk"))
    if not tag_ids or len(tags) != len(tag_ids):
        raise ValidationFailed(details={"tag_ids": "须选择不重复且已启用的标签"})
    return tags


def _replace_tags(recruitment, tags):
    """将招募标签关联调整为给定集合。

    保留仍需要的关联，删除多余关联并补齐缺失项。

    Args:
        recruitment: 当前事务中的招募。
        tags: 已校验并锁定的标签序列。
    """
    wanted = {tag.pk for tag in tags}
    links = RecruitmentTag.objects.filter(recruitment=recruitment)
    links.exclude(tag_id__in=wanted).delete()
    present = set(links.values_list("tag_id", flat=True))
    RecruitmentTag.objects.bulk_create([
        RecruitmentTag(recruitment=recruitment, tag=tag) for tag in tags if tag.pk not in present
    ])


def _active_applications(recruitment):
    """锁定变更前仍有效的申请，供通知和失效处理使用。

    Args:
        recruitment: 当前事务已加锁的招募。

    Returns:
        list[Application]: 按主键排序的 processing/accepted 申请，预加载申请人。

    Raises:
        RuntimeError: 没有当前事务的有效招募锁。
    """
    tx.assert_recruitment_locked(recruitment)
    return list(
        Application.objects.select_for_update(of=("self",)).select_related("applicant")
        .filter(recruitment=recruitment, status__in=ACTIVE_APPLICATION_STATUSES).order_by("pk")
    )


def _notify_applicants(recruitment, applications, notification_type):
    """为指定申请集合写入关联招募通知。

    必须在业务事务内调用；接收范围由调用方决定。

    Args:
        recruitment: 关联招募。
        applications: 已按通知接收范围筛选的申请序列。
        notification_type: 通知类型常量。
    """
    for application in applications:
        notify(
            recipient=application.applicant, type=notification_type,
            recruitment=recruitment, application=application,
        )


def create_recruitment(user, *, data: dict):
    """创建招募及标签关联，任一写入失败时整体回滚。

    Args:
        user: 已认证发布者，学生与教师使用相同规则。
        data: 经 RecruitmentWriteSerializer 校验的数据，须含标题、类型、描述、人数上限、截止时间和 tag_ids。

    Returns:
        Recruitment: 已提交的新招募。

    Raises:
        NotAuthenticated: 用户未认证。
        ValidationFailed: 截止时间、人数或标签不合法。
        RuntimeError: 调用方已在事务内。
    """
    _require_user(user)
    tx.assert_not_in_atomic()
    with transaction.atomic():
        now = clock.now()
        rules.validate_deadline(data["deadline"], now)
        rules.validate_headcount(data.get("min_headcount"), data["max_headcount"])
        tags = _active_tags(data["tag_ids"])
        values = {field: data[field] for field in CONTENT_FIELDS if field in data}
        recruitment = Recruitment.objects.create(publisher=user, **values)
        _replace_tags(recruitment, tags)
    return recruitment


def update_recruitment(user, recruitment_id: int, *, data: dict):
    """修改开放窗口内的招募，并原子更新关联状态和通知。

    先独立提交到期补执行。更新通知只发给变更前 processing/accepted 申请人；人数上限降至已接受人数时进入 full 并拒绝其余处理中申请。
    内容与标签集合均未变化时不写入新版本或通知；相同内容的并发请求在锁内合并为一次有效变更。

    Args:
        user: 招募发布者。
        recruitment_id: 招募主键。
        data: 已校验的非空部分更新字段，未提供的字段保持原值。

    Returns:
        Recruitment: 业务事务提交后的招募对象。

    Raises:
        BizError: 未认证、对象不可见、非发布者、不可编辑，或人数/时间/标签校验失败。
        RuntimeError: 调用方已在事务内。
    """
    _preflight(user, recruitment_id)

    def update(locked, now):
        _authorize(user, locked)
        if not policies.can_edit(user, locked, now):
            raise Conflict(ErrorCode.RECRUITMENT_NOT_EDITABLE)
        changed = [field for field in CONTENT_FIELDS if field in data and getattr(locked, field) != data[field]]
        for field in changed:
            setattr(locked, field, data[field])
        rules.validate_deadline(locked.deadline, now)
        rules.validate_headcount(locked.min_headcount, locked.max_headcount)
        if locked.max_headcount < locked.accepted_count:
            raise Conflict(ErrorCode.HEADCOUNT_BELOW_ACCEPTED)
        tags = _active_tags(data["tag_ids"]) if "tag_ids" in data else None
        tags_changed = tags is not None and {tag.pk for tag in tags} != set(
            RecruitmentTag.objects.filter(recruitment=locked).values_list("tag_id", flat=True)
        )
        if not changed and not tags_changed:
            return locked
        if tags_changed:
            _replace_tags(locked, tags)
        applications = _active_applications(locked)
        # 变更前仍有效的申请人收到招募更新；若随后满员，再收到各自处理结果。
        _notify_applicants(locked, applications, types.RECRUITMENT_UPDATED)
        if locked.max_headcount == locked.accepted_count:
            state.mark_full(locked, now, extra_update_fields=changed)
        else:
            locked.save(update_fields=[*changed, "updated_at"])
        return locked

    return state.run_in_recruitment_tx(recruitment_id, update)


def close_recruitment(user, recruitment_id: int):
    """由发布者手动关闭招募，保留已有申请的七天处理窗口。

    Args:
        user: 招募发布者。
        recruitment_id: 招募主键。

    Returns:
        Recruitment: 已提交的关闭状态对象。

    Raises:
        BizError: 未认证、对象不可见、非发布者或招募已不允许关闭。
        RuntimeError: 调用方已在事务内。
    """
    _preflight(user, recruitment_id)

    def close(locked, now):
        _authorize(user, locked)
        if not policies.can_close(user, locked, now):
            raise Conflict(ErrorCode.RECRUITMENT_NOT_EDITABLE)
        locked.status = RecruitmentStatus.CLOSED
        locked.closed_at = now
        locked.close_reason = CloseReason.MANUAL
        locked.save(update_fields=["status", "closed_at", "close_reason", "updated_at"])
        notify(
            recipient=locked.publisher, type=types.RECRUITMENT_CLOSED,
            recruitment=locked, context={"auto": False},
        )
        return locked

    return state.run_in_recruitment_tx(recruitment_id, close)


def _delete_recruitment(user, recruitment_id: int, *, reason: str | None, governance: bool):
    """按明确的操作入口删除招聘，原子保存失效事件、人数、通知与审计。"""
    _preflight(user, recruitment_id, allow_admin=governance)
    if reason is not None and (not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500):
        raise ValidationFailed(details={"reason": "删除原因须为 1 至 500 字"})
    reason = reason.strip() if reason is not None else None
    if governance and not reason:
        raise ValidationFailed(details={"reason": "治理删除必须填写原因"})

    def delete(locked, now):
        _authorize(user, locked, allow_admin=governance)
        if not governance and not policies.can_delete(user, locked, now):
            raise Conflict(ErrorCode.RECRUITMENT_NOT_EDITABLE)
        applications = _active_applications(locked)
        record_status_changes(
            locked, applications, to_status=ApplicationStatus.INVALID,
            reason=ApplicationHistoryReason.DELETE_INVALID, occurred_at=now, actor=user,
        )
        locked.deleted_at = now
        locked.accepted_count = 0
        locked.save(update_fields=["deleted_at", "accepted_count", "updated_at"])
        Application.objects.filter(
            pk__in=[app.pk for app in applications if app.status == ApplicationStatus.PROCESSING],
        ).update(
            status=ApplicationStatus.INVALID, decided_at=now,
            publisher_mark=PublisherMark.NONE, has_unseen_update=False, updated_at=now,
        )
        Application.objects.filter(
            pk__in=[app.pk for app in applications if app.status == ApplicationStatus.ACCEPTED],
        ).update(
            status=ApplicationStatus.INVALID,
            publisher_mark=PublisherMark.NONE, has_unseen_update=False, updated_at=now,
        )
        _notify_applicants(locked, applications, types.RECRUITMENT_DELETED)
        if governance:
            notify(
                recipient=locked.publisher, type=types.ADMIN_REMOVED, recruitment=locked,
                context={"reason_label": reason},
            )
        record(
            actor=user, action=actions.ADMIN_DELETE if governance else actions.RECRUITMENT_DELETE,
            target_type="recruitment", target_id=locked.pk, reason=reason,
        )

    state.run_in_recruitment_tx(recruitment_id, delete)


def delete_recruitment(user, recruitment_id: int, *, reason: str | None = None):
    """发布者在开放窗口内删除本人招聘，管理员标记不改变限制。

    Args:
        user: 已认证招聘发布者。
        recruitment_id: 目标招聘主键。
        reason: 可选的非空原因，最多 500 字。

    Returns:
        None: 有效申请失效、接受人数归零，保留业务状态及时间，不删除简历。

    Raises:
        BizError: 对象不可见、非发布者、删除窗口关闭或原因无效。
        RuntimeError: 调用方已处于事务中。
    """
    _delete_recruitment(user, recruitment_id, reason=reason, governance=False)


def governance_delete_recruitment(user, recruitment_id: int, *, reason: str):
    """管理员治理删除任意未删除状态的招聘，并向发布者发送处置原因。

    Args:
        user: 当前有效的业务管理员，权限在锁内重新读取。
        recruitment_id: 目标招聘主键。
        reason: 必填非空原因，最多 500 字。

    Returns:
        None: 删除、状态历史、人数及通知与审计同事务提交。

    Raises:
        BizError: 对象不存在或已删除、管理员权限不足或原因不合法。
        RuntimeError: 调用方已处于事务中。
    """
    _delete_recruitment(user, recruitment_id, reason=reason, governance=True)
