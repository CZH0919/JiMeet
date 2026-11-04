"""申请查询及只读时间投影；在分页前应用归属、留存与状态过滤。"""

from copy import copy
from datetime import timedelta

from django.db.models import Case, CharField, DateTimeField, F, Q, Value, When
from django.db.models.functions import Coalesce, Least

from apps.applications.models import Application
from apps.applications.policies import resolve_application_access
from apps.core.choices import ApplicationStatus, PublisherMark, RecruitmentStatus
from apps.core.errors import NotFound, NotFoundAsDenied
from apps.recruitments import rules
from apps.recruitments.models import Recruitment
from apps.recruitments.selectors import project_recruitment


def project_application(application, now):
    """生成符合当前时间的申请与招募只读快照。

    不写入状态、通知或已阅标记；原模型对象保持不变。

    Args:
        application: 已加载 recruitment 的申请对象。
        now: 带时区的业务时间。

    Returns:
        Application: 浅拷贝的申请；七天处理期到期时将 processing 投影为 rejected 并裁剪标记。
    """
    projected = copy(application)
    projected.recruitment = project_recruitment(application.recruitment, now)
    end = rules.seven_day_deadline(projected.recruitment)
    if projected.status == ApplicationStatus.PROCESSING and end is not None and now >= end:
        projected.status = ApplicationStatus.REJECTED
        projected.decided_at = end
        projected.publisher_mark = PublisherMark.NONE
        projected.has_unseen_update = False
    return projected


def require_application_access(user, application, now):
    """校验业务关系及留存期限，拒绝时隐藏对象存在性。

    Args:
        user: 当前操作者。
        application: 已完成时间投影的申请快照。
        now: 留存判断时间点。

    Returns:
        ApplicationAccess: 允许访问时的字段权限。

    Raises:
        NotFoundAsDenied: 无申请人/发布者关系或留存到期，映射为 404 并保留拒绝审计目标。
    """
    access = resolve_application_access(user, application, application.recruitment, now)
    if not access.can_view:
        raise NotFoundAsDenied("申请不存在", audit_target=("application", application.pk))
    return access


def get_application(user, application_id: int, now):
    """查询申请，完成时间投影及对象可见性校验。

    Args:
        user: 当前操作者。
        application_id: 申请主键。
        now: 带时区的业务时间。

    Returns:
        Application: 预加载招募与申请人的已鉴权快照。

    Raises:
        NotFound: 申请不存在。
        NotFoundAsDenied: 无业务关系或已过留存期。
    """
    try:
        application = Application.objects.select_related("recruitment", "applicant").get(pk=application_id)
    except Application.DoesNotExist:
        raise NotFound("申请不存在") from None
    projected = project_application(application, now)
    require_application_access(user, projected, now)
    return projected


def get_publisher_recruitment(user, recruitment_id: int, now):
    """查询发布者可查看申请历史的招募范围。

    Args:
        user: 当前操作者，必须为发布者。
        recruitment_id: 招募主键。
        now: 留存及时间状态判断时点。

    Returns:
        Recruitment: 已投影的招募；留存期内允许已删除招募的受限申请历史。

    Raises:
        NotFound: 招募不存在。
        NotFoundAsDenied: 操作者不是发布者，或留存期已结束。
    """
    try:
        recruitment = Recruitment.objects.get(pk=recruitment_id)
    except Recruitment.DoesNotExist:
        raise NotFound("招募不存在") from None
    recruitment = project_recruitment(recruitment, now)
    if user.pk != recruitment.publisher_id or rules.is_retention_expired(recruitment, now):
        raise NotFoundAsDenied("招募不存在", audit_target=("recruitment", recruitment.pk))
    return recruitment


def list_applications(*, filters: dict, now, applicant=None, recruitment=None):
    """在分页前按归属、留存期限及有效状态过滤申请。

    返回模型仍需 project_application 后序列化；数据库过滤使用相同的有效状态，但不更新模型字段。

    Args:
        filters: 已校验的 status、recruitment_id 等条件。
        now: 判断关闭、七天期限及 180 天留存的时间点。
        applicant: 本人申请列表的用户范围，默认 None。
        recruitment: 发布者申请列表的已鉴权招募范围，默认 None。

    Returns:
        QuerySet[Application]: 按 created_at、主键倒序排列，预加载招募及申请人。

    Raises:
        ValueError: applicant 和 recruitment 同时提供或同时省略。
    """
    if (applicant is None) == (recruitment is None):
        raise ValueError("必须且只能提供一个申请查询范围")
    queryset = Application.objects.select_related("recruitment", "applicant")
    if applicant is not None:
        queryset = queryset.filter(applicant=applicant)
    else:
        queryset = queryset.filter(recruitment=recruitment)
    if "recruitment_id" in filters:
        queryset = queryset.filter(recruitment_id=filters["recruitment_id"])
    # 任务尚未执行时也从实际截止时间计算关闭、拒绝和留存终点。
    queryset = queryset.alias(
        effective_closed_at=Case(
            When(
                recruitment__status=RecruitmentStatus.OPEN, recruitment__deadline__lte=now,
                then=Coalesce("recruitment__closed_at", "recruitment__deadline"),
            ),
            default=F("recruitment__closed_at"), output_field=DateTimeField(),
        ),
    ).alias(
        retention_start=Least("effective_closed_at", "recruitment__full_at", "recruitment__deleted_at"),
        effective_status=Case(
            When(
                status=ApplicationStatus.PROCESSING, effective_closed_at__lte=now - timedelta(days=7),
                then=Value(ApplicationStatus.REJECTED),
            ),
            default=F("status"), output_field=CharField(),
        ),
    ).filter(Q(retention_start__isnull=True) | Q(retention_start__gt=now - timedelta(days=180)))
    if "status" in filters:
        queryset = queryset.filter(effective_status=filters["status"])
    return queryset.order_by("-created_at", "-pk")
