"""招募只读查询、时间状态投影及详情权限上下文。"""

from copy import copy

from django.db.models import Case, CharField, Count, F, IntegerField, Prefetch, Q, Value, When

from apps.applications.models import Application
from apps.applications.policies import can_submit_application
from apps.core.choices import ApplicationStatus, CloseReason, RecruitmentStatus
from apps.core.errors import BizError, NotFound
from apps.recruitments import policies, rules
from apps.recruitments.models import Recruitment, Tag


def list_tags():
    """返回可选标签；停用标签只从新建选择列表移除。"""
    return Tag.objects.filter(is_active=True).order_by("sort_order", "pk")


def _related_recruitments():
    return Recruitment.objects.select_related("publisher").prefetch_related(
        Prefetch("tags", queryset=Tag.objects.order_by("sort_order", "pk")),
    )


def list_recruitments(*, filters: dict, now, publisher=None):
    """在数据库内按有效状态过滤、排序；返回可交给公共分页工具的查询集。"""
    queryset = _related_recruitments().filter(deleted_at__isnull=True).annotate(
        display_status=Case(
            When(status=RecruitmentStatus.OPEN, deadline__lte=now, then=Value(RecruitmentStatus.CLOSED)),
            default=F("status"), output_field=CharField(),
        ),
    )
    if publisher is not None:
        queryset = queryset.filter(publisher=publisher)
    if filters.get("q"):
        queryset = queryset.filter(Q(title__icontains=filters["q"]) | Q(description__icontains=filters["q"]))
    if "type" in filters:
        queryset = queryset.filter(type=filters["type"])
    if "tag" in filters:
        queryset = queryset.filter(tags__pk=filters["tag"])
    if "status" in filters:
        queryset = queryset.filter(display_status=filters["status"])
    return queryset.annotate(
        display_order=Case(
            When(display_status=RecruitmentStatus.OPEN, then=Value(0)),
            default=Value(1), output_field=IntegerField(),
        ),
    ).order_by("display_order", "-created_at", "-pk")


def get_recruitment(recruitment_id: int):
    """普通详情统一隐藏已删除招募，包含发布者和管理员访问。"""
    try:
        return _related_recruitments().get(pk=recruitment_id, deleted_at__isnull=True)
    except Recruitment.DoesNotExist:
        raise NotFound("招募不存在") from None


def project_recruitment(recruitment, now):
    """复制只读快照并补足展示时间；不保存模型、不生成通知。"""
    projected = copy(recruitment)
    if projected.status == RecruitmentStatus.OPEN and now >= projected.deadline:
        projected.status = RecruitmentStatus.CLOSED
        if projected.closed_at is None:
            projected.closed_at = projected.deadline
            projected.close_reason = CloseReason.DEADLINE
    return projected


def _effective_application_status(status, recruitment, now):
    end = rules.seven_day_deadline(recruitment)
    if status == ApplicationStatus.PROCESSING and end is not None and now >= end:
        return ApplicationStatus.REJECTED
    return status


def count_applications(recruitment, now) -> dict:
    """仅供发布者详情使用；清理后读取聚合值，不恢复个人记录。"""
    counts = dict.fromkeys(ApplicationStatus.values, 0)
    if recruitment.applications_anonymized_at is not None:
        stored = recruitment.application_status_counts or {}
        return {status: stored.get(status, 0) for status in counts}
    for group in Application.objects.filter(recruitment=recruitment).values("status").annotate(total=Count("pk")):
        status = _effective_application_status(group["status"], recruitment, now)
        counts[status] += group["total"]
    return counts


def detail_context(recruitment, user, now) -> dict:
    """针对当前用户构造最少必要的申请摘要及权限；管理员不额外读取申请。"""
    expired = rules.is_retention_expired(recruitment, now)
    latest = None
    has_active = False
    if not expired:
        mine = Application.objects.filter(recruitment=recruitment, applicant=user)
        latest = mine.order_by("-created_at", "-pk").values("id", "status").first()
        has_active = mine.exclude(status=ApplicationStatus.WITHDRAWN).exists()
        if latest is not None:
            latest["status"] = _effective_application_status(latest["status"], recruitment, now)
    try:
        can_submit_application(user, recruitment, now, has_active_application=has_active)
    except BizError as error:
        apply_reason = error.code
    else:
        apply_reason = None
    owner = policies.can_view_applications(user, recruitment)
    context = {
        "my_application": latest,
        "permissions": {
            "can_apply": apply_reason is None,
            "apply_blocked_reason": apply_reason,
            "can_edit": policies.can_edit(user, recruitment, now),
            "can_close": policies.can_close(user, recruitment, now),
            "can_delete": policies.can_delete(user, recruitment, now),
            "can_view_applications": owner and not expired,
        },
    }
    if owner:
        context["application_counts"] = count_applications(recruitment, now)
    return context
