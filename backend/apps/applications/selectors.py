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
    """复制申请快照；到七天边界时投影拒绝，不写状态、通知或未读标记。"""
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
    """统一隐去无业务关系或已过留存期的对象，同时保留拒绝审计目标。"""
    access = resolve_application_access(user, application, application.recruitment, now)
    if not access.can_view:
        raise NotFoundAsDenied("申请不存在", audit_target=("application", application.pk))
    return access


def get_application(user, application_id: int, now):
    """返回已鉴权的只读申请快照，关联对象一次加载。"""
    try:
        application = Application.objects.select_related("recruitment", "applicant").get(pk=application_id)
    except Application.DoesNotExist:
        raise NotFound("申请不存在") from None
    projected = project_application(application, now)
    require_application_access(user, projected, now)
    return projected


def get_publisher_recruitment(user, recruitment_id: int, now):
    """发布者可在留存期内查询删除后的历史；管理员没有额外权限。"""
    try:
        recruitment = Recruitment.objects.get(pk=recruitment_id)
    except Recruitment.DoesNotExist:
        raise NotFound("招募不存在") from None
    recruitment = project_recruitment(recruitment, now)
    if user.pk != recruitment.publisher_id or rules.is_retention_expired(recruitment, now):
        raise NotFoundAsDenied("招募不存在", audit_target=("recruitment", recruitment.pk))
    return recruitment


def list_applications(*, filters: dict, now, applicant=None, recruitment=None):
    """查询必须限定申请人或已鉴权招募；SQL 与详情使用相同的时间边界。"""
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
