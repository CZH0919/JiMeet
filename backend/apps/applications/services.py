"""申请提交、修改及状态变更。"""

from apps.applications.models import Application
from apps.applications.policies import can_submit_application, require_submit_identity
from apps.applications.selectors import get_application, require_application_access
from apps.audit import actions
from apps.audit.service import record
from apps.core import clock, tx
from apps.core.choices import ApplicationStatus, PublisherMark, RecruitmentStatus
from apps.core.errors import Conflict, ErrorCode, Forbidden, NotFound
from apps.files.storage import discard_resume, staged_resume
from apps.notifications import types
from apps.notifications.service import notify
from apps.recruitments.models import Recruitment
from apps.recruitments import rules
from apps.recruitments.state import mark_full, run_in_recruitment_tx


def _record_application_update(user, application):
    record(
        actor=user, action=actions.APPLICATION_UPDATE,
        target_type="application", target_id=application.pk,
    )


def submit_application(user, recruitment_id: int, *, resume, note: str | None = None):
    """返回已提交的申请；业务失败清理新文件，已提交的到期补处理独立保留。"""
    tx.assert_not_in_atomic()
    try:
        recruitment = Recruitment.objects.get(pk=recruitment_id, deleted_at__isnull=True)
    except Recruitment.DoesNotExist:
        raise NotFound("招募不存在") from None
    require_submit_identity(user, recruitment)
    with staged_resume(resume) as stored:
        def create(locked, now):
            if locked.deleted_at is not None:
                raise NotFound("招募不存在")
            active = Application.objects.filter(recruitment=locked, applicant=user).exclude(
                status=ApplicationStatus.WITHDRAWN,
            ).exists()
            can_submit_application(user, locked, now, has_active_application=active)
            application = Application.objects.create(
                recruitment=locked, applicant=user, note=note,
                resume_file=stored.path, resume_name=stored.original_name,
                resume_size=stored.size, resume_type=stored.type,
            )
            notify(
                recipient=locked.publisher, type=types.APPLICATION_SUBMITTED,
                recruitment=locked, application=application,
            )
            return application

        return run_in_recruitment_tx(recruitment_id, create)


def _update_locked_application(user, application_id: int, update):
    """按招聘、申请的固定顺序加锁后执行一个申请写操作。"""
    recruitment_id = tx.peek_application_recruitment_id(application_id)

    def apply(locked_recruitment, now):
        application = tx.lock_application(application_id, locked_recruitment)
        require_application_access(user, application, now)
        return update(locked_recruitment, application, now)

    return run_in_recruitment_tx(recruitment_id, apply)


def modify_application(user, application_id: int, *, note=None, resume=None, update_note=False):
    """修改处理中申请；替换简历在数据库提交后才清理旧文件。"""
    tx.assert_not_in_atomic()
    if resume is None:
        _save_application_update(
            user, application_id, note=note, update_note=update_note,
        )
        return get_application(user, application_id, clock.now())

    with staged_resume(resume) as stored:
        application, old_resume_path = _save_application_update(
            user, application_id, note=note, update_note=update_note, stored_resume=stored,
        )
    if old_resume_path and old_resume_path != stored.path:
        discard_resume(old_resume_path)
    return get_application(user, application_id, clock.now())


def _save_application_update(
    user, application_id: int, *, note=None, update_note: bool, stored_resume=None,
):
    def update(recruitment, application, now):
        if application.applicant_id != user.pk:
            raise Forbidden("只有申请人本人可以修改申请")
        if application.status != ApplicationStatus.PROCESSING:
            raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING, "申请已不是处理中，不能修改")
        if recruitment.deleted_at is not None:
            raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING, "申请已失效，不能修改")

        update_fields = ["has_unseen_update", "updated_at"]
        application.has_unseen_update = True
        if update_note:
            application.note = note
            update_fields.append("note")
        old_resume_path = None
        if stored_resume is not None:
            old_resume_path = application.resume_file.name
            application.resume_file = stored_resume.path
            application.resume_name = stored_resume.original_name
            application.resume_size = stored_resume.size
            application.resume_type = stored_resume.type
            update_fields.extend(["resume_file", "resume_name", "resume_size", "resume_type"])
        application.save(update_fields=update_fields)
        notify(
            recipient=recruitment.publisher, type=types.APPLICATION_UPDATED,
            recruitment=recruitment, application=application,
        )
        _record_application_update(user, application)
        return application, old_resume_path

    return _update_locked_application(user, application_id, update)


def perform_application_action(user, application_id: int, action: str, *, seen_updated_at=None):
    """执行撤回、发布者处理或修改已阅确认，并返回更新后的详情快照。"""
    tx.assert_not_in_atomic()
    allowed = {"withdraw", "accept", "reject", "hold", "unhold", "read"}
    if action not in allowed:
        raise ValueError(f"未知申请操作: {action}")

    def update(recruitment, application, now):
        if action == "withdraw":
            if application.applicant_id != user.pk:
                raise Forbidden("只有申请人本人可以撤回申请")
            if application.status != ApplicationStatus.PROCESSING:
                raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING, "申请已不是处理中，不能撤回")
            if recruitment.deleted_at is not None:
                raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING, "申请已失效，不能撤回")
            application.status = ApplicationStatus.WITHDRAWN
            application.publisher_mark = PublisherMark.NONE
            application.has_unseen_update = False
            application.decided_at = now
            application.save(update_fields=[
                "status", "publisher_mark", "has_unseen_update", "decided_at", "updated_at",
            ])
            notify(
                recipient=recruitment.publisher, type=types.APPLICATION_WITHDRAWN,
                recruitment=recruitment, application=application,
            )
            _record_application_update(user, application)
            return application

        if action == "read":
            if recruitment.publisher_id != user.pk:
                raise Forbidden("只有发布者可以确认申请修改")
            if application.status in {ApplicationStatus.WITHDRAWN, ApplicationStatus.INVALID}:
                raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING, "该申请不能确认修改")
            if application.has_unseen_update and application.updated_at == seen_updated_at:
                application.has_unseen_update = False
                application.save(update_fields=["has_unseen_update"])
            return application

        if recruitment.publisher_id != user.pk:
            raise Forbidden("只有发布者可以处理申请")
        if application.status != ApplicationStatus.PROCESSING:
            raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING, "申请已不是处理中，不能再处理")
        if not rules.is_processable(recruitment, now):
            code = (
                ErrorCode.RECRUITMENT_FULL
                if recruitment.status == RecruitmentStatus.FULL
                else ErrorCode.PROCESSING_WINDOW_CLOSED
            )
            message = "招聘已满员" if code == ErrorCode.RECRUITMENT_FULL else "招聘处理窗口已关闭"
            raise Conflict(code, message)

        target_mark = {
            "hold": PublisherMark.HOLD,
            "unhold": PublisherMark.NONE,
        }.get(action)
        if target_mark is not None:
            if application.publisher_mark != target_mark:
                application.publisher_mark = target_mark
                application.save(update_fields=["publisher_mark", "updated_at"])
                _record_application_update(user, application)
            return application

        application.publisher_mark = PublisherMark.NONE
        application.has_unseen_update = False
        application.decided_at = now
        if action == "accept":
            application.status = ApplicationStatus.ACCEPTED
            application.save(update_fields=[
                "status", "publisher_mark", "has_unseen_update", "decided_at", "updated_at",
            ])
            recruitment.accepted_count += 1
            if recruitment.accepted_count >= recruitment.max_headcount:
                mark_full(recruitment, now)
            else:
                recruitment.save(update_fields=["accepted_count", "updated_at"])
            notify(
                recipient=application.applicant, type=types.APPLICATION_ACCEPTED,
                recruitment=recruitment, application=application,
            )
            _record_application_update(user, application)
            return application

        application.status = ApplicationStatus.REJECTED
        application.save(update_fields=[
            "status", "publisher_mark", "has_unseen_update", "decided_at", "updated_at",
        ])
        notify(
            recipient=application.applicant, type=types.APPLICATION_REJECTED,
            recruitment=recruitment, application=application,
        )
        _record_application_update(user, application)
        return application

    _update_locked_application(user, application_id, update)
    return get_application(user, application_id, clock.now())
