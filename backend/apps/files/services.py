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
    """鉴权下载结果：已打开的流、展示文件名和可信响应 MIME 类型。"""
    stream: BinaryIO
    filename: str
    content_type: str


def download_resume(user, application_id: int) -> ResumeDownload:
    """在短事务内复核申请权限、打开简历并记录发布者下载审计。

    锁顺序为招募再申请；失败时关闭已打开的句柄，申请人下载不记发布者查看审计。

    Args:
        user: 当前申请人或招募发布者，管理员身份不额外授权。
        application_id: 申请主键。

    Returns:
        ResumeDownload: 成功后由调用方或 FileResponse 关闭 stream，传输在事务外进行。

    Raises:
        NotFound: 申请不可见，或文件缺失/路径不可用。
        Forbidden: 申请已撤回、失效或招聘已删除，发布者无下载权限。
        RuntimeError: 调用方处于事务中。
        OSError: 其他未转换的文件系统读取错误。
    """
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
