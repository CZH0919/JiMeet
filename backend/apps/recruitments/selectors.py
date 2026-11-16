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
    """查询可用于新招募选择的启用标签。

    Returns:
        QuerySet[Tag]: 按 sort_order、主键升序排列的标签，不改变已有招募的停用标签关联。
    """
    return Tag.objects.filter(is_active=True).order_by("sort_order", "pk")


def _related_recruitments():
    """构造预加载发布者与有序标签的招募查询集。

    Returns:
        QuerySet[Recruitment]: 尚未按删除状态或权限过滤的基础查询集。
    """
    return Recruitment.objects.select_related("publisher").prefetch_related(
        Prefetch("tags", queryset=Tag.objects.order_by("sort_order", "pk")),
    )


def list_recruitments(*, filters: dict, now, publisher=None):
    """按有效展示状态过滤未删除招募。

    读取不会持久化到期关闭或生成通知。

    Args:
        filters: 已校验的 q、type、tag、status 等查询条件；分页由调用方执行。
        now: 判断截止状态的带时区时间。
        publisher: 可选发布者；提供时限定本人发布列表。

    Returns:
        QuerySet[Recruitment]: 开放招募优先，其后按 created_at、主键倒序排列。
    """
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
    """查询未删除招募及其发布者和标签。

    Args:
        recruitment_id: 招募主键。

    Returns:
        Recruitment: 关联数据已预加载的模型对象。

    Raises:
        NotFound: 招募不存在或已软删除，发布者和管理员也不能通过该入口查看已删除详情。
    """
    try:
        return _related_recruitments().get(pk=recruitment_id, deleted_at__isnull=True)
    except Recruitment.DoesNotExist:
        raise NotFound("招募不存在") from None


def project_recruitment(recruitment, now):
    """构造符合当前时间的只读招募快照。

    Args:
        recruitment: 原招募对象。
        now: 判断截止状态的带时区时间。

    Returns:
        Recruitment: 浅拷贝对象；已到期的 open 投影为 closed，原对象和数据库不变。
    """
    projected = copy(recruitment)
    if projected.deleted_at is None and projected.status == RecruitmentStatus.OPEN and now >= projected.deadline:
        projected.status = RecruitmentStatus.CLOSED
        if projected.closed_at is None:
            projected.closed_at = projected.deadline
            projected.close_reason = CloseReason.DEADLINE
    return projected


def _effective_application_status(status, recruitment, now):
    """计算满员或关闭后七天边界上的申请展示状态。

    Args:
        status: 已保存的申请状态。
        recruitment: 已完成时间投影的招募对象。
        now: 判断状态的带时区时间。

    Returns:
        str: 未删除招聘已满员或到达七天边界时 processing 显示为 rejected，其余保留原值。
    """
    if recruitment.deleted_at is not None:
        return status
    if status == ApplicationStatus.PROCESSING and recruitment.status == RecruitmentStatus.FULL:
        return ApplicationStatus.REJECTED
    end = rules.seven_day_deadline(recruitment)
    if status == ApplicationStatus.PROCESSING and end is not None and now >= end:
        return ApplicationStatus.REJECTED
    return status


def count_applications(recruitment, now) -> dict:
    """统计有效展示状态下的申请数量。

    Args:
        recruitment: 已完成时间投影的招募；调用方负责发布者权限校验。
        now: 统计时点。

    Returns:
        dict: 五种申请状态对应的数量；如已有留存清理聚合值则优先使用。
    """
    counts = dict.fromkeys(ApplicationStatus.values, 0)
    if recruitment.applications_anonymized_at is not None:
        stored = recruitment.application_status_counts or {}
        return {status: stored.get(status, 0) for status in counts}
    for group in Application.objects.filter(recruitment=recruitment).values("status").annotate(total=Count("pk")):
        status = _effective_application_status(group["status"], recruitment, now)
        counts[status] += group["total"]
    return counts


def detail_context(recruitment, user, now) -> dict:
    """生成当前用户的申请摘要及招募操作权限。

    管理员不额外读取他人的申请。权限字段用于展示，写服务仍须在锁内复核。

    Args:
        recruitment: 已完成时间投影的招募对象。
        user: 已认证当前用户。
        now: 判断操作窗口的时间点。

    Returns:
        dict: my_application、permissions；仅发布者另含 application_counts。
    """
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
            "can_govern_delete": policies.can_govern_delete(user, recruitment),
            "can_view_applications": owner,
        },
    }
    if owner:
        context["application_counts"] = count_applications(recruitment, now)
    return context
