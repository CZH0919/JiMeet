"""申请内容与操作的统一权限出口，不在权限判断中查询数据库。"""
import logging
from dataclasses import dataclass
from typing import Literal

from apps.core.choices import ApplicationStatus
from apps.core.errors import Conflict, ErrorCode, Forbidden, NotAuthenticated
from apps.recruitments import rules

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplicationAccess:
    """
    申请记录与敏感字段的可见性，管理员没有额外读取权限。

    ### 字段说明
    - relation: 申请人与发布者的关系，none 表示无关系
    - can_view: 是否可查看申请记录
    - can_see_note: 是否可查看申请备注
    - can_see_applicant_name: 是否可查看申请人姓名
    - can_download_resume: 是否可下载简历文件
    - can_see_publisher_mark: 是否可查看发布者标记
    
    """

    relation: Literal["applicant", "publisher", "none"]
    can_view: bool
    can_see_note: bool
    can_see_applicant_name: bool
    can_download_resume: bool
    can_see_publisher_mark: bool


def _is_user(user, user_id) -> bool:
    return bool(user and user.is_authenticated and user.pk == user_id)


def resolve_application_access(user, app, recruitment, now) -> ApplicationAccess:
    """
    按对象关系、留存期限和申请状态解析字段权限。

    申请人和发布者身份不可能同时成立，若同时成立则记录错误日志。
    Args:
        user: 当前操作者
        app: 申请对象
        recruitment: 申请对应的招聘对象
        now: 当前时间，UTC 时区
    Returns:
        ApplicationAccess 对象
    """
    publisher = _is_user(user, recruitment.publisher_id)
    applicant = _is_user(user, app.applicant_id)
    if publisher and applicant:
        logger.error("申请人与发布者相同", extra={"application_id": app.pk})
    relation = "publisher" if publisher else "applicant" if applicant else "none"
    if relation == "none" or rules.is_retention_expired(recruitment, now):
        return ApplicationAccess(relation, False, False, False, False, False)
    restricted = app.status in {ApplicationStatus.WITHDRAWN, ApplicationStatus.INVALID}
    return ApplicationAccess(
        relation=relation,
        can_view=True,
        can_see_note=not publisher or not restricted,
        can_see_applicant_name=publisher,
        can_download_resume=not restricted,
        can_see_publisher_mark=publisher and not restricted,
    )


def can_submit_application(user, recruitment, now, *, has_active_application: bool) -> None:
    """依次校验本人投递、隐私确认、开放窗口及调用方查得的重复记录。"""
    if _is_user(user, recruitment.publisher_id):
        raise Forbidden("不能申请本人发布的招聘", code=ErrorCode.SELF_APPLICATION_FORBIDDEN)
    if not user or not user.is_authenticated:
        raise NotAuthenticated()
    if user.privacy_consented_at is None:
        raise Forbidden("请先确认个人信息处理告知", code=ErrorCode.PRIVACY_NOT_CONSENTED)
    if not rules.is_apply_open(recruitment, now):
        raise Conflict(ErrorCode.RECRUITMENT_NOT_OPEN, "招聘当前不可投递")
    if has_active_application:
        raise Conflict(ErrorCode.DUPLICATE_APPLICATION, "已存在未撤回的申请")


def can_modify_application(user, app, recruitment) -> bool:
    """申请人可修改未删除招聘下仍在处理中的申请，调用前须补执行状态。"""
    return (
        _is_user(user, app.applicant_id)
        and app.status == ApplicationStatus.PROCESSING
        and recruitment.deleted_at is None
    )


def can_withdraw_application(user, app, recruitment) -> bool:
    """撤回条件与修改一致。"""
    return can_modify_application(user, app, recruitment)


def can_process_application(user, app, recruitment, now) -> bool:
    """仅发布者可在处理窗口内处理 processing 申请。"""
    return (
        _is_user(user, recruitment.publisher_id)
        and app.status == ApplicationStatus.PROCESSING
        and rules.is_processable(recruitment, now)
    )
