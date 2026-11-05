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
    """判断已认证用户主键是否匹配。

    Args:
        user: 当前用户，可为 None 或匿名用户。
        user_id: 需要匹配的数据库用户主键。

    Returns:
        bool: 是否匹配。
    """
    return bool(user and user.is_authenticated and user.pk == user_id)


def resolve_application_access(user, app, recruitment, now) -> ApplicationAccess:
    """按关系、申请状态和留存期限计算字段读取权限。

    管理员无额外读取权限；withdrawn/invalid 禁止双方下载简历，并对发布者隐藏说明及私有标记。

    Args:
        user: 当前操作者。
        app: 已补执行或完成时间投影的申请。
        recruitment: 对应的已补执行或投影招募。
        now: 带时区的业务时间。

    Returns:
        ApplicationAccess: 记录、说明、姓名、简历及发布者私有标记的可见性。
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


def require_submit_identity(user, recruitment) -> None:
    """在文件暂存前校验申请身份和隐私确认。

    Args:
        user: 当前申请人。
        recruitment: 目标招募对象。

    Raises:
        NotAuthenticated: 用户未认证。
        Forbidden: 申请本人发布的招募，或未确认隐私告知；分别使用 SELF_APPLICATION_FORBIDDEN、PRIVACY_NOT_CONSENTED。
    """
    if _is_user(user, recruitment.publisher_id):
        raise Forbidden("不能申请本人发布的招聘", code=ErrorCode.SELF_APPLICATION_FORBIDDEN)
    if not user or not user.is_authenticated:
        raise NotAuthenticated()
    if user.privacy_consented_at is None:
        raise Forbidden("请先确认个人信息处理告知", code=ErrorCode.PRIVACY_NOT_CONSENTED)


def can_submit_application(user, recruitment, now, *, has_active_application: bool) -> None:
    """校验投递身份、开放窗口及重复申请限制。

    Args:
        user: 当前申请人。
        recruitment: 已锁定并补执行状态的招募。
        now: 带时区的业务时间。
        has_active_application: 调用方在锁内查询出的是否已有未撤回申请。

    Returns:
        None: 校验成功；本函数不返回权限布尔值。

    Raises:
        NotAuthenticated: 用户未认证。
        Forbidden: 本人投递或隐私未确认。
        Conflict: 招募不可投递或已有未撤回申请，分别使用 RECRUITMENT_NOT_OPEN、DUPLICATE_APPLICATION。
    """
    require_submit_identity(user, recruitment)
    if not rules.is_apply_open(recruitment, now):
        raise Conflict(ErrorCode.RECRUITMENT_NOT_OPEN, "招聘当前不可投递")
    if has_active_application:
        raise Conflict(ErrorCode.DUPLICATE_APPLICATION, "已存在未撤回的申请")


def can_modify_application(user, app, recruitment) -> bool:
    """判断申请人能否修改当前申请。

    对象可见性及留存判断由调用方先行完成。

    Args:
        user: 当前用户。
        app: 已补执行或完成时间投影的申请。
        recruitment: 对应招募。

    Returns:
        bool: 申请人身份匹配、申请为 processing 且招募未删除时为 True。
    """
    return (
        _is_user(user, app.applicant_id)
        and app.status == ApplicationStatus.PROCESSING
        and recruitment.deleted_at is None
    )


def can_withdraw_application(user, app, recruitment) -> bool:
    """判断申请人能否撤回当前申请。

    对象可见性及留存判断由调用方先行完成。

    Args:
        user: 当前用户。
        app: 已补执行或完成时间投影的申请。
        recruitment: 对应招募。

    Returns:
        bool: 申请人身份匹配、申请为 processing 且招募未删除时为 True。
    """
    return can_modify_application(user, app, recruitment)


def can_process_application(user, app, recruitment, now) -> bool:
    """判断发布者能否在处理窗口内处理申请。

    Args:
        user: 当前用户。
        app: 已补执行或投影的申请。
        recruitment: 对应招募。
        now: 带时区的业务时间。

    Returns:
        bool: 发布者身份匹配、申请为 processing 且仍可处理时为 True。
    """
    return (
        _is_user(user, recruitment.publisher_id)
        and app.status == ApplicationStatus.PROCESSING
        and rules.is_processable(recruitment, now)
    )
