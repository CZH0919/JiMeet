"""简历受控读取；打开文件与审计处于短事务，文件传输在事务外进行。"""

from dataclasses import dataclass
from typing import BinaryIO

from django.db import transaction

from apps.applications.selectors import get_application, project_application, require_application_access
from apps.audit import actions
from apps.audit.service import record
from apps.core import clock, tx
from apps.core.errors import Forbidden, NotFound
from apps.files.storage import open_resume
from apps.files.validators import clean_resume_name

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True)
class ResumeDownload:
    stream: BinaryIO
    filename: str
    content_type: str


def download_resume(user, application_id: int) -> ResumeDownload:
    """按招募、申请顺序锁定并复核权限；失败关闭句柄，成功由响应负责关闭。"""
    tx.assert_not_in_atomic()
    application = get_application(user, application_id, clock.now())
    stream = None
    try:
        with tx.recruitment_lock_scope(), transaction.atomic():
            recruitment = tx.lock_recruitment(application.recruitment_id)
            application = tx.lock_application(application_id, recruitment)
            application.recruitment = recruitment
            now = clock.now()
            application = project_application(application, now)
            access = require_application_access(user, application, now)
            if not access.can_download_resume:
                raise Forbidden("当前申请状态不允许下载简历", audit_target=("application", application_id))
            try:
                stream = open_resume(application.resume_file.name)
            except (FileNotFoundError, PermissionError, ValueError):
                raise NotFound("简历文件不可用") from None
            if access.relation == "publisher":
                record(actor=user, action=actions.RESUME_VIEW, target_type="application", target_id=application_id)
            result = ResumeDownload(
                stream=stream,
                filename=clean_resume_name(application.resume_name, application.resume_type),
                content_type=CONTENT_TYPES[application.resume_type],
            )
        return result
    except BaseException:
        if stream is not None:
            stream.close()
        raise
