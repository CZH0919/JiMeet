"""公告与投稿写入函数：每个函数在一个事务内锁行、复核状态与权限，写表并写审计。

视图层做请求入口校验；业务层在行锁内做最终权限与状态复核：
发布要求当前管理员；本人删除要求当前管理员与作者身份；
治理删除要求当前管理员与非空原因。Sprint3 起公告不可编辑，投稿提交后
不可改稿、撤回。

所有公告删除（本人删除与治理删除）在同一事务内通知发布人与投稿人，
两者相同只通知一次；重复删除、重复审核只产生一次业务结果及对应审计与通知。
审核通过按投稿原文生成正式公告（发布人记审核管理员、投稿人另记），
驳回必填理由；领取 15 分钟内有效，主动交回或到期后原领取人不能再凭旧
领取记录提交处理结果。
"""
from datetime import timedelta
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.announcements.models import Announcement, AnnouncementSubmission
from apps.audit import actions
from apps.audit.service import record
from apps.core.clock import now
from apps.core.errors import Conflict, ErrorCode, Forbidden, NotFound
from apps.notifications import types
from apps.notifications.service import notify

TARGET_TYPE = "announcement"
SUBMISSION_TARGET_TYPE = "announcement_submission"
CLAIM_TTL = timedelta(minutes=15)
CLAIM_FIELDS = ("claimed_by", "claimed_until", "claim_id")
DAILY_SUBMISSION_LIMIT = 5
PENDING_SUBMISSION_LIMIT = 5


def _require_current_admin(actor) -> None:
    """在业务事务内锁定管理员身份，与停用账号、撤销权限串行。"""
    if not User.objects.select_for_update(no_key=True).filter(pk=actor.pk, is_active=True, is_admin=True).exists():
        raise Forbidden("需要管理员权限")


def _lock_and_check(announcement_id: int, *, actor, require_author: bool):
    """锁定公告行并复核存在性与当前权限。

    Args:
        announcement_id: 公告主键。
        actor: 操作者；在锁内刷新其管理员状态，捕获并发撤权。
        require_author: True 时同时要求操作者为公告作者（本人删除）。

    Returns:
        Announcement: 已锁定且未删除的公告对象。

    Raises:
        NotFound: 公告不存在或已删除。
        Forbidden: 操作者当前无管理员权限，或要求作者身份时不匹配。
    """
    _require_current_admin(actor)
    try:
        locked = Announcement.objects.select_for_update().get(pk=announcement_id)
    except Announcement.DoesNotExist:
        raise NotFound("公告不存在") from None
    if locked.deleted_at is not None:
        raise NotFound("公告不存在")
    if require_author and locked.author_id != actor.pk:
        raise Forbidden("仅公告作者可执行该操作")
    return locked


def _notify_deletion(announcement: Announcement, *, by_admin: bool, reason: str | None) -> None:
    """删除结果通知发布人与投稿人，两者相同只通知一次。"""
    notice_type = types.ANNOUNCEMENT_ADMIN_REMOVED if by_admin else types.ANNOUNCEMENT_REMOVED
    context = {"announcement_title": announcement.title}
    if by_admin and reason:
        context["reason_label"] = reason
    recipients = [announcement.author]
    if announcement.submitted_by_id and announcement.submitted_by_id != announcement.author_id:
        recipients.append(announcement.submitted_by)
    for recipient in recipients:
        if recipient.cancelled_at is not None:
            continue
        notify(
            recipient=recipient, type=notice_type, announcement=announcement, context=context,
        )


def create_announcement(
    *, actor, title, content, time_kind, event_at, link_url=None, recruitment=None,
    submitted_by=None,
) -> Announcement:
    """创建公告并记录 announcement_publish 审计；要求操作者当前为管理员。

    Args:
        actor: 发布者，须为当前管理员（直接发布或投稿审核通过的审核人）。
        title: 竞赛或活动名称。
        content: 公告正文。
        time_kind: deadline 或 event。
        event_at: 与 time_kind 对应的时间。
        link_url: 可空的相关网站。
        recruitment: 可空的关联招募对象。
        submitted_by: 可空的投稿人；审核通过生成的公告填写。

    Returns:
        Announcement: 新建的公告。

    Raises:
        Forbidden: 操作者当前不具管理员权限。
    """
    with transaction.atomic():
        _require_current_admin(actor)
        announcement = Announcement.objects.create(
            author=actor,
            submitted_by=submitted_by,
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


def soft_delete_announcement(announcement_id: int, *, actor) -> Announcement:
    """本人软删除公告：审计与删除结果通知（发布人、投稿人）同事务提交。

    Args:
        announcement_id: 公告主键。
        actor: 操作者，须为当前管理员且是公告作者。

    Returns:
        Announcement: 已设置 deleted_at 的公告。

    Raises:
        NotFound: 公告不存在或已删除；重复删除返回同一结果，不重复写审计与通知。
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
        _notify_deletion(locked, by_admin=False, reason=None)
    return locked


def governance_delete_announcement(announcement_id: int, *, actor, reason: str) -> Announcement:
    """治理删除公告：软删除、审计与删除结果通知同事务提交。

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
        _notify_deletion(locked, by_admin=True, reason=reason.strip()[:500])
    return locked


def _day_start(moment):
    """上海自然日的起点时刻。"""
    return moment.astimezone(timezone.get_current_timezone()).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def create_submission(
    *, submitter, title, content, time_kind, event_at, link_url=None,
) -> AnnouncementSubmission:
    """提交公告投稿（待审稿）；上海自然日每人最多 5 条、同时待审最多 5 条。

    提交后不能改稿、撤回；驳回后再次投稿按一条新投稿占用额度。

    Args:
        submitter: 当前已启用、无管理员权限的投稿人。
        title: 竞赛或活动名称。
        content: 投稿正文。
        time_kind: deadline 或 event。
        event_at: 与 time_kind 对应的时间。
        link_url: 可空的报名方式及链接。

    Returns:
        AnnouncementSubmission: 新建的待审投稿。

    Raises:
        Forbidden: 账号不可用，或当前管理员应直接发布公告。
        Conflict: 当日投稿数或待审数已达上限（含本次提交），SUBMISSION_LIMIT_EXCEEDED。
    """
    with transaction.atomic():
        # 账号行锁使身份变更和同一投稿人的额度判定串行。
        account = User.objects.select_for_update(no_key=True).only("is_active", "is_admin").get(pk=submitter.pk)
        if not account.is_active:
            raise Forbidden("账号已停用")
        if account.is_admin:
            raise Forbidden("管理员请使用公告直接发布入口")
        moment = now()
        same_day = AnnouncementSubmission.objects.filter(
            submitter=submitter, submitted_at__gte=_day_start(moment),
        ).count()
        pending = AnnouncementSubmission.objects.filter(
            submitter=submitter, status=AnnouncementSubmission.STATUS_PENDING,
        ).count()
        if same_day + 1 > DAILY_SUBMISSION_LIMIT or pending + 1 > PENDING_SUBMISSION_LIMIT:
            raise Conflict(
                ErrorCode.SUBMISSION_LIMIT_EXCEEDED,
                "今日投稿数或待审投稿数已达上限，请稍后再试",
            )
        return AnnouncementSubmission.objects.create(
            submitter=submitter, title=title, content=content,
            time_kind=time_kind, event_at=event_at, link_url=link_url,
        )


def _lock_submission(submission_id: int, *, actor):
    """锁定投稿行并复核管理员权限与待审状态。"""
    _require_current_admin(actor)
    try:
        locked = AnnouncementSubmission.objects.select_for_update().get(pk=submission_id)
    except AnnouncementSubmission.DoesNotExist:
        raise NotFound("投稿不存在") from None
    if locked.status != AnnouncementSubmission.STATUS_PENDING:
        raise Conflict(ErrorCode.SUBMISSION_ALREADY_PROCESSED, "投稿已被处理")
    return locked


def _require_claim(locked: AnnouncementSubmission, *, actor, claim_id: UUID, moment) -> None:
    """校验当前领取人、批次和到期时刻。"""
    if (
        locked.claimed_by_id != actor.pk or locked.claim_id is None or locked.claim_id != claim_id
        or locked.claimed_until is None or moment >= locked.claimed_until
    ):
        raise Conflict(ErrorCode.SUBMISSION_LOCKED, "领取已失效，请刷新待审列表")


def _clear_claim(locked: AnnouncementSubmission) -> None:
    """清空领取信息，由调用方与审核状态一并保存。"""
    locked.claimed_by = None
    locked.claimed_until = None
    locked.claim_id = None


def claim_submission(submission_id: int, *, actor) -> AnnouncementSubmission:
    """领取投稿审核权（15 分钟）；他人有效领取期间不可抢占。

    Args:
        submission_id: 投稿主键。
        actor: 领取的管理员。

    Returns:
        AnnouncementSubmission: 更新领取信息的投稿。

    Raises:
        NotFound: 投稿不存在。
        Forbidden: 操作者当前无管理员权限。
        Conflict: 投稿已被处理（SUBMISSION_ALREADY_PROCESSED）或他人领取中（SUBMISSION_LOCKED）。
    """
    with transaction.atomic():
        locked = _lock_submission(submission_id, actor=actor)
        moment = now()
        active = locked.claimed_by_id and locked.claimed_until and locked.claimed_until > moment
        if active:
            if locked.claimed_by_id != actor.pk:
                raise Conflict(ErrorCode.SUBMISSION_LOCKED, "该投稿已被其他管理员领取")
            if locked.claim_id is not None:
                return locked
        else:
            locked.claimed_by = actor
            locked.claimed_until = moment + CLAIM_TTL
        # 升级前的有效领取由原领取人补取批次，沿用原截止时间。
        locked.claim_id = uuid4()
        locked.save(update_fields=CLAIM_FIELDS)
    return locked


def release_submission(submission_id: int, *, actor, claim_id: UUID) -> AnnouncementSubmission:
    """主动交回领取的投稿；交回后原领取人不能再凭旧领取记录处理。

    Args:
        submission_id: 投稿主键。
        actor: 当前领取人。
        claim_id: 本次领取返回的批次标识。

    Returns:
        AnnouncementSubmission: 已清除领取信息的投稿。

    Raises:
        NotFound: 投稿不存在。
        Forbidden: 操作者当前无管理员权限。
        Conflict: 投稿已被处理或操作者不是领取人。
    """
    with transaction.atomic():
        locked = _lock_submission(submission_id, actor=actor)
        _require_claim(locked, actor=actor, claim_id=claim_id, moment=now())
        _clear_claim(locked)
        locked.save(update_fields=CLAIM_FIELDS)
    return locked


def approve_submission(submission_id: int, *, actor, claim_id: UUID) -> AnnouncementSubmission:
    """审核通过投稿：按投稿原文生成公告，发布人记审核人、投稿人另记。

    审核结果、审计与投稿人站内通知同事务提交。

    Args:
        submission_id: 投稿主键。
        actor: 审核的管理员，须持有有效领取。
        claim_id: 本次领取返回的批次标识。

    Returns:
        AnnouncementSubmission: 状态为 approved 的投稿。

    Raises:
        NotFound: 投稿不存在。
        Forbidden: 操作者当前无管理员权限。
        Conflict: 投稿已被处理，或领取缺失/过期/非本人。
    """
    with transaction.atomic():
        locked = _lock_submission(submission_id, actor=actor)
        moment = now()
        _require_claim(locked, actor=actor, claim_id=claim_id, moment=moment)
        announcement = Announcement.objects.create(
            author=actor,
            submitted_by=locked.submitter,
            title=locked.title,
            content=locked.content,
            time_kind=locked.time_kind,
            event_at=locked.event_at,
            link_url=locked.link_url,
        )
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_PUBLISH,
            target_type=TARGET_TYPE,
            target_id=announcement.pk,
        )
        locked.status = AnnouncementSubmission.STATUS_APPROVED
        locked.reviewed_by = actor
        locked.reviewed_at = moment
        locked.announcement = announcement
        _clear_claim(locked)
        locked.save(update_fields=["status", "reviewed_by", "reviewed_at", "announcement", *CLAIM_FIELDS])
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_SUBMISSION_APPROVE,
            target_type=SUBMISSION_TARGET_TYPE,
            target_id=locked.pk,
        )
        notify(
            recipient=locked.submitter,
            type=types.ANNOUNCEMENT_SUBMISSION_APPROVED,
            announcement=announcement,
            context={"announcement_title": locked.title},
        )
    return locked


def reject_submission(submission_id: int, *, actor, claim_id: UUID, reason: str) -> AnnouncementSubmission:
    """驳回投稿：必填理由；审核结果、审计与投稿人站内通知同事务提交。

    Args:
        submission_id: 投稿主键。
        actor: 审核的管理员，须持有有效领取。
        claim_id: 本次领取返回的批次标识。
        reason: 非空驳回理由。

    Returns:
        AnnouncementSubmission: 状态为 rejected 的投稿。

    Raises:
        NotFound: 投稿不存在。
        Forbidden: 操作者当前无管理员权限。
        Conflict: 投稿已被处理，或领取缺失/过期/非本人。
        ValueError: 理由为空。
    """
    if not (reason and reason.strip()):
        raise ValueError("驳回必须填写理由")
    with transaction.atomic():
        locked = _lock_submission(submission_id, actor=actor)
        moment = now()
        _require_claim(locked, actor=actor, claim_id=claim_id, moment=moment)
        locked.status = AnnouncementSubmission.STATUS_REJECTED
        locked.reviewed_by = actor
        locked.reviewed_at = moment
        locked.reject_reason = reason.strip()[:500]
        _clear_claim(locked)
        locked.save(update_fields=["status", "reviewed_by", "reviewed_at", "reject_reason", *CLAIM_FIELDS])
        record(
            actor=actor,
            action=actions.ANNOUNCEMENT_SUBMISSION_REJECT,
            target_type=SUBMISSION_TARGET_TYPE,
            target_id=locked.pk,
            reason=reason.strip()[:500],
        )
        notify(
            recipient=locked.submitter,
            type=types.ANNOUNCEMENT_SUBMISSION_REJECTED,
            announcement=None,
            context={"announcement_title": locked.title, "reason_label": reason.strip()[:500]},
        )
    return locked
