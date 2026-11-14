"""申请提交、修改及状态变更。"""

from apps.applications.history import record_status_changes
from apps.applications.models import Application, ApplicationHistoryReason
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
    """记录申请写操作的审计，不保存说明或简历内容。

    Args:
        user: 当前操作者。
        application: 业务事务中的申请对象。
    """
    record(
        actor=user, action=actions.APPLICATION_UPDATE,
        target_type="application", target_id=application.pk,
    )


def submit_application(user, recruitment_id: int, *, resume, note: str | None = None):
    """提交简历申请，原子创建申请及发布者通知。

    文件校验与暂存在事务外进行；业务失败清理新文件，但已提交的到期补执行不回滚。

    Args:
        user: 已认证申请人，须确认隐私告知且不能是招募发布者。
        recruitment_id: 招募主键。
        resume: 支持 name、size、read、seek、tell 的上传文件，限非空 PDF/DOC/DOCX 且不超过 10 MiB。
        note: 经序列化器规范化的可选说明，默认 None。

    Returns:
        Application: 已提交的新申请，初始状态为 processing。

    Raises:
        BizError: 对象不可见、身份或隐私校验失败、窗口关闭、重复申请或简历无效。
        RuntimeError: 调用方已处于事务中。
        OSError: 私有存储创建或写入失败。
    """
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
    """按招募、申请顺序加锁并复核可见性，再执行回调。

    回调异常原样传播；状态补执行与业务操作分属两个事务。

    Args:
        user: 当前操作者。
        application_id: 申请主键。
        update: 接收 (招募, 申请, 业务时间) 的回调；状态与具体操作权限由回调校验。

    Returns:
        object: 业务回调的返回值。

    Raises:
        BizError: 申请不存在或不可见。
        RuntimeError: 调用方已处于事务中。
    """
    recruitment_id = tx.peek_application_recruitment_id(application_id)

    def apply(locked_recruitment, now):
        application = tx.lock_application(application_id, locked_recruitment)
        require_application_access(user, application, now)
        return update(locked_recruitment, application, now)

    return run_in_recruitment_tx(recruitment_id, apply)


def modify_application(user, application_id: int, *, note=None, resume=None, update_note=False):
    """修改本人的处理中申请，并标记发布者尚未读取更新。

    替换成功提交后尝试清理旧文件，清理失败仅记日志；业务失败清理新文件。更新通知与审计随业务事务提交。

    Args:
        user: 申请人本人。
        application_id: 申请主键。
        note: 规范化说明；仅在 update_note=True 时写入，None 可用于清空。
        resume: 可选新上传文件，默认 None 表示不替换。
        update_note: 是否修改说明，默认 False；请求至少提供一个字段由输入层保证。

    Returns:
        Application: 更新后重新鉴权及时间投影的快照。

    Raises:
        BizError: 对象不可见、非申请人、状态不允许修改，或简历校验失败。
        RuntimeError: 调用方已在事务内。
        OSError: 新简历存储失败。
    """
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
    """在锁内保存申请说明或暂存简历的元数据。

    Args:
        user: 当前申请人。
        application_id: 申请主键。
        note: 规范化的新说明，默认 None。
        update_note: 是否写入说明，必须明确提供。
        stored_resume: 可选的 StoredResume；文件已由调用方暂存。

    Returns:
        tuple: (已保存的申请, 被替换的旧文件相对路径或 None)。

    Raises:
        BizError: 对象不可见、非申请人或申请不可修改。
    """
    def update(recruitment, application, now):
        if application.applicant_id != user.pk:
            raise Forbidden("只有申请人本人可以修改申请")
        if application.status != ApplicationStatus.PROCESSING:
            raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING, "申请已不是处理中，不能修改")
        if recruitment.deleted_at is not None:
            raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING, "申请已失效，不能修改")
        if not rules.is_processable(recruitment, now):
            raise Conflict(ErrorCode.PROCESSING_WINDOW_CLOSED, "申请修改窗口已关闭")

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
    """执行撤回、发布者处理或修改已阅确认。

    接受到最后名额时原子进入 full 并拒绝剩余申请。hold/unhold 目标已满足时幂等；read 仅在版本匹配时清除更新标记，不修改内容版本时间。

    Args:
        user: 当前操作者；withdraw 要求申请人，其余动作要求发布者。
        application_id: 申请主键。
        action: withdraw、accept、reject、hold、unhold 或 read。
        seen_updated_at: read 使用的带时区内容版本时间，其他动作应省略；输入层负责必填校验。

    Returns:
        Application: 动作完成后重新鉴权及时间投影的快照。

    Raises:
        ValueError: action 不在允许集合。
        BizError: 对象不可见、操作者不符、申请已终态或处理窗口已关闭。
        RuntimeError: 调用方已处于事务中。
    """
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
            if not rules.is_processable(recruitment, now):
                raise Conflict(ErrorCode.PROCESSING_WINDOW_CLOSED, "申请撤回窗口已关闭")
            record_status_changes(
                recruitment, [application], to_status=ApplicationStatus.WITHDRAWN,
                reason=ApplicationHistoryReason.WITHDRAW, occurred_at=now, actor=user,
            )
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
            if recruitment.deleted_at is not None or application.status in {ApplicationStatus.WITHDRAWN, ApplicationStatus.INVALID}:
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
            record_status_changes(
                recruitment, [application], to_status=ApplicationStatus.ACCEPTED,
                reason=ApplicationHistoryReason.ACCEPT, occurred_at=now, actor=user,
            )
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

        record_status_changes(
            recruitment, [application], to_status=ApplicationStatus.REJECTED,
            reason=ApplicationHistoryReason.REJECT_MANUAL, occurred_at=now, actor=user,
        )
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
