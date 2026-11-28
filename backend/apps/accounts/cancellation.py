"""账号注销的业务事务及私有数据清除。"""
from uuid import uuid4

from django.db import transaction
from django.db.models import Q

from apps.accounts import ratelimit, verification
from apps.accounts.locking import lock_active_user
from apps.accounts.models import User
from apps.announcements.models import Announcement, AnnouncementSubmission
from apps.applications.history import record_status_changes
from apps.applications.models import Application, ApplicationHistoryReason, ApplicationStatusHistory
from apps.audit import actions
from apps.audit.models import AuditLog
from apps.audit.service import detach_actors, record
from apps.chat import selectors as chat
from apps.chat.models import ChatConversation, ChatMessage, ChatSendPause
from apps.core import clock, tx
from apps.core.choices import ApplicationStatus, CloseReason, PublisherMark, RecruitmentStatus
from apps.notifications import types
from apps.notifications.models import EmailLog, Notification
from apps.notifications.service import notify
from apps.recruitments import rules, state
from apps.recruitments.lifecycle import details_expired
from apps.recruitments.models import Recruitment
from apps.recruitments.retention import erase_applications, erase_notifications, purge_locked


def _stop_publishing(job, moment):
    """关闭投递入口并处理无人继续审核的申请，保留其他申请人的历史结果。"""
    if job.deleted_at is not None:
        return
    was_open = job.status == RecruitmentStatus.OPEN
    if was_open:
        reached_deadline = job.deadline <= moment
        if job.closed_at is None:
            job.closed_at = job.deadline if reached_deadline else moment
            job.close_reason = CloseReason.DEADLINE if reached_deadline else CloseReason.MANUAL
        job.status = RecruitmentStatus.CLOSED
        job.save(update_fields=["status", "closed_at", "close_reason", "updated_at"])
    if job.status == RecruitmentStatus.FULL:
        state.reject_processing_applications(job, job.full_at, "full")
        return
    end = rules.seven_day_deadline(job)
    if end is not None and end <= moment:
        state.reject_processing_applications(job, end, "closed_timeout")
        return
    pending = list(job.applications.filter(status=ApplicationStatus.PROCESSING).select_related("applicant"))
    record_status_changes(job, pending, to_status=ApplicationStatus.REJECTED,
                          reason=ApplicationHistoryReason.PUBLISHER_CANCELLED, occurred_at=moment)
    job.applications.filter(status=ApplicationStatus.PROCESSING).update(
        status=ApplicationStatus.REJECTED, decided_at=moment, publisher_mark=PublisherMark.NONE,
        has_unseen_update=False, updated_at=moment,
    )
    for application in pending:
        notify(recipient=application.applicant, type=types.APPLICATION_REJECTED, recruitment=job,
               application=application, context={"reason_label": "发布者已注销，招聘停止处理"})
    if was_open:
        for app in job.applications.filter(status=ApplicationStatus.ACCEPTED).select_related("applicant"):
            notify(recipient=app.applicant, type=types.RECRUITMENT_UPDATED, recruitment=job,
                   application=app, context={"reason_label": "发布者已注销，招聘已关闭，原录取结果保留"})


def _erase_applicant(job, user, moment):
    """移除该申请人的各次投递，按有效状态计入匿名统计，录取名额继续占用。"""
    applications = job.applications.filter(applicant=user)
    counts = job.anonymous_counts.copy()
    withdrawn = False
    for status in applications.order_by().values_list("status", flat=True):
        status = rules.effective_application_status(status, job, moment)
        if status == ApplicationStatus.PROCESSING:
            status = ApplicationStatus.WITHDRAWN
            withdrawn = True
        counts[status] = counts.get(status, 0) + 1
    if counts != job.anonymous_counts:
        job.anonymous_counts = counts
        job.save(update_fields=["anonymous_counts"])
        erase_applications(applications)
    if withdrawn and job.publisher.cancelled_at is None:
        notify(recipient=job.publisher, type=types.ANONYMOUS_WITHDRAWAL, recruitment=job)


def _unlink_public_records(user, moment):
    """让历史发布记录共用不可登录的匿名所有者，不保留原发布账号的关联。"""
    jobs = Recruitment.objects.filter(publisher=user)
    notices = Announcement.objects.filter(author=user)
    history = ApplicationStatusHistory.objects.filter(actor=user)
    if jobs.exists() or notices.exists() or history.exists():
        anonymous, _ = User.objects.get_or_create(
            real_id="!unlinked-public",
            defaults={"name": "已注销用户", "nickname": "已注销用户", "email": "unlinked-public@deleted.invalid",
                      "password": "!", "is_active": False, "cancelled_at": moment, "role": "student",
                      "email_notify_enabled": False},
        )
        if anonymous.cancelled_at is None or anonymous.is_active:
            raise RuntimeError("匿名所有者状态无效")
        jobs.update(publisher=anonymous)
        notices.update(author=anonymous)
        history.update(actor=anonymous)
    AnnouncementSubmission.objects.filter(reviewed_by=user).update(reviewed_by=None)


def _clear_chat(user, moment):
    conversations = ChatConversation.objects.select_for_update(no_key=True).filter(
        Q(user_low=user) | Q(user_high=user),
    ).order_by("pk")
    for conversation in conversations:
        ChatMessage.objects.filter(conversation=conversation, sender=user).delete()
        last = chat.visible_messages(moment).filter(conversation=conversation).order_by("-created_at", "-pk")
        conversation.last_message_at = last.values_list("created_at", flat=True).first()
        conversation.save(update_fields=["last_message_at"])
    ChatSendPause.objects.filter(user=user).delete()


@transaction.atomic
def cancel_account(user):
    """注销已确认的本人账号，并在提交后清除已撤销访问的简历。

    账号、招聘及会话依次加锁。失败时回滚业务变更和文件任务。保留的审计
    使用去标识审计编号，保留操作时身份快照。新注册账号使用独立主键和公开编号。
    """
    user = lock_active_user(user)
    moment = clock.now()
    verification.revoke_email_proofs(user.email)
    for kind in (ratelimit.KIND_REGISTER, ratelimit.KIND_LOGIN):
        ratelimit.clear_failures(scope="email", value=user.email.lower(), kind=kind)
    affected = Recruitment.objects.filter(
        Q(publisher=user) | Q(pk__in=Application.objects.filter(applicant=user).values("recruitment_id")),
    ).order_by("pk").values_list("pk", flat=True)
    for pk in list(affected):
        with tx.recruitment_lock_scope():
            job = tx.lock_recruitment(pk)
            if details_expired(job, moment):
                purge_locked(job, moment)
            else:
                if job.publisher_id == user.pk:
                    _stop_publishing(job, moment)
                _erase_applicant(job, user, moment)
    _unlink_public_records(user, moment)
    _clear_chat(user, moment)
    AnnouncementSubmission.objects.filter(submitter=user).delete()
    AnnouncementSubmission.objects.filter(claimed_by=user).update(claimed_by=None, claimed_until=None, claim_id=None)
    Announcement.objects.filter(submitted_by=user).update(submitted_by=None)
    erase_notifications(Notification.objects.filter(recipient=user))
    EmailLog.objects.filter(to_email__iexact=user.email).delete()
    record(actor=user, action=actions.ACCOUNT_CANCEL, target_type="account", target_id=user.pk)
    detach_actors(AuditLog.objects.filter(actor=user))
    user.groups.clear()
    user.user_permissions.clear()
    user.set_unusable_password()
    token = uuid4().hex
    User.objects.filter(pk=user.pk).update(
        uid=uuid4().hex, real_id=token, email=f"{token}@deleted.invalid", nickname="已注销用户", name="已注销用户",
        sso_subject=None, email_verified_at=None, privacy_consented_at=None, email_notify_enabled=False,
        is_active=False, is_admin=False, is_staff=False, is_superuser=False, last_login=None, role="student",
        password=user.password, created_at=moment, updated_at=moment, cancelled_at=moment,
    )
