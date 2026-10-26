"""招募写服务：权限复核、事务、关联申请、通知与删除审计。"""

from django.db import transaction

from apps.applications.models import Application
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
    if not user or not user.is_authenticated:
        raise NotAuthenticated()


def _authorize(user, recruitment, *, allow_admin=False):
    if recruitment.deleted_at is not None:
        raise NotFound("招募不存在")
    if user.pk != recruitment.publisher_id and not (allow_admin and user.is_admin):
        raise Forbidden(audit_target=("recruitment", recruitment.pk))


def _preflight(user, recruitment_id, *, allow_admin=False):
    """补执行前先拒绝无权用户；业务事务加锁后仍须再次检查。"""
    _require_user(user)
    try:
        recruitment = Recruitment.objects.only("id", "publisher_id", "deleted_at").get(pk=recruitment_id)
    except Recruitment.DoesNotExist:
        raise NotFound("招募不存在") from None
    _authorize(user, recruitment, allow_admin=allow_admin)


def _active_tags(tag_ids):
    """事务内按固定顺序锁标签，防止写入时标签被并发停用。"""
    tags = list(Tag.objects.select_for_update().filter(pk__in=tag_ids, is_active=True).order_by("pk"))
    if not tag_ids or len(tags) != len(tag_ids):
        raise ValidationFailed(details={"tag_ids": "须选择不重复且已启用的标签"})
    return tags


def _replace_tags(recruitment, tags):
    wanted = {tag.pk for tag in tags}
    links = RecruitmentTag.objects.filter(recruitment=recruitment)
    links.exclude(tag_id__in=wanted).delete()
    present = set(links.values_list("tag_id", flat=True))
    RecruitmentTag.objects.bulk_create([
        RecruitmentTag(recruitment=recruitment, tag=tag) for tag in tags if tag.pk not in present
    ])


def _active_applications(recruitment):
    tx.assert_recruitment_locked(recruitment)
    return list(
        Application.objects.select_for_update(of=("self",)).select_related("applicant")
        .filter(recruitment=recruitment, status__in=ACTIVE_APPLICATION_STATUSES).order_by("pk")
    )


def _notify_applicants(recruitment, applications, notification_type):
    for application in applications:
        notify(
            recipient=application.applicant, type=notification_type,
            recruitment=recruitment, application=application,
        )


def create_recruitment(user, *, data: dict):
    """保存已通过输入序列化器校验的数据；招募与标签失败时整体回滚。"""
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
    """合并部分字段后校验；满员变更与关联申请处理在同一业务事务提交。"""
    _preflight(user, recruitment_id)

    def update(locked, now):
        _authorize(user, locked)
        if not policies.can_edit(user, locked, now):
            raise Conflict(ErrorCode.RECRUITMENT_NOT_EDITABLE)
        for field in CONTENT_FIELDS:
            if field in data:
                setattr(locked, field, data[field])
        rules.validate_deadline(locked.deadline, now)
        rules.validate_headcount(locked.min_headcount, locked.max_headcount)
        if locked.max_headcount < locked.accepted_count:
            raise Conflict(ErrorCode.HEADCOUNT_BELOW_ACCEPTED)
        if "tag_ids" in data:
            _replace_tags(locked, _active_tags(data["tag_ids"]))
        applications = _active_applications(locked)
        changed = [field for field in CONTENT_FIELDS if field in data]
        # 变更前仍有效的申请人收到招募更新；若随后满员，再收到各自处理结果。
        _notify_applicants(locked, applications, types.RECRUITMENT_UPDATED)
        if locked.max_headcount == locked.accepted_count:
            state.mark_full(locked, now, extra_update_fields=changed)
        else:
            locked.save(update_fields=[*changed, "updated_at"])
        return locked

    return state.run_in_recruitment_tx(recruitment_id, update)


def close_recruitment(user, recruitment_id: int):
    """发布者手动关闭；已有申请保留七天处理窗口，不立即拒绝。"""
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


def delete_recruitment(user, recruitment_id: int, *, reason: str | None = None):
    """软删除并使有效申请失效；状态、通知及删除审计原子提交。"""
    _preflight(user, recruitment_id, allow_admin=True)
    if user.is_admin and not (reason and reason.strip()):
        raise ValidationFailed(details={"reason": "管理员删除必须填写原因"})

    def delete(locked, now):
        _authorize(user, locked, allow_admin=True)
        if not policies.can_delete(user, locked, now):
            raise Conflict(ErrorCode.RECRUITMENT_NOT_EDITABLE)
        applications = _active_applications(locked)
        locked.deleted_at = now
        locked.save(update_fields=["deleted_at", "updated_at"])
        # 已接受申请保留首次决定时间，历史接受人数也不递减。
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
        if user.is_admin:
            notify(recipient=locked.publisher, type=types.ADMIN_REMOVED, recruitment=locked)
        record(
            actor=user, action=actions.ADMIN_DELETE if user.is_admin else actions.RECRUITMENT_DELETE,
            target_type="recruitment", target_id=locked.pk, reason=reason,
        )

    state.run_in_recruitment_tx(recruitment_id, delete)
