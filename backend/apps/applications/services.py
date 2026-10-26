"""申请提交：事务外暂存简历，招募锁内复核并原子创建申请及通知。"""

from apps.applications.models import Application
from apps.applications.policies import can_submit_application, require_submit_identity
from apps.core import tx
from apps.core.choices import ApplicationStatus
from apps.core.errors import NotFound
from apps.files.storage import staged_resume
from apps.notifications import types
from apps.notifications.service import notify
from apps.recruitments.models import Recruitment
from apps.recruitments.state import run_in_recruitment_tx


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
