"""公告的 HTTP 入口，完整请求与字段契约见 backend/design_file/api.md 第 8 章。

需认证的入口先检查会话和 CSRF，分别拒绝为 401 和 403；非法查询或请求数据通常返回 400。
入口层做权限快检（无权 403），业务服务在锁内做最终权限与状态复核。
"""
from apps.announcements import selectors, services
from apps.announcements.models import Announcement
from apps.announcements.serializers import (
    AnnouncementCreateSerializer,
    AnnouncementQuerySerializer,
    AnnouncementSerializer,
    AnnouncementUpdateSerializer,
    GovernanceDeleteSerializer,
)
from apps.core.errors import Forbidden, NotFound, ValidationFailed
from apps.core.pagination import paginate
from apps.core.responses import created, ok, page
from apps.core.serializers import EmptyBodySerializer
from apps.core.views import PrivateAPIView, validate_data
from apps.core.permissions import IsAdminFlag


def _load_or_404(announcement_id: int) -> Announcement:
    """读取未删除公告，不存在或已删除按 404 处理。

    Args:
        announcement_id: 公告主键。

    Returns:
        Announcement: 未删除的公告对象。

    Raises:
        NotFound: 公告不存在或已删除。
    """
    announcement = Announcement.objects.select_related("author", "recruitment").filter(
        pk=announcement_id, deleted_at__isnull=True
    ).first()
    if announcement is None:
        raise NotFound("公告不存在")
    return announcement


def _require_author_admin(request, announcement) -> None:
    """编辑与本人删除的入口校验：当前管理员且为作者。

    Args:
        request: 当前请求。
        announcement: 目标公告。

    Raises:
        Forbidden: 无管理员权限或非作者。
    """
    IsAdminFlag().has_permission(request, None)
    if announcement.author_id != request.user.pk:
        raise Forbidden("仅公告作者可执行该操作")


def _resolve_recruitment(recruitment_id):
    """解析关联招募；须存在且未删除。

    Args:
        recruitment_id: 招募主键或 None。

    Returns:
        Recruitment | None: 未删除的招募对象；None 原样返回。

    Raises:
        ValidationFailed: 招募不存在或已删除。
    """
    if recruitment_id is None:
        return None
    from apps.recruitments.models import Recruitment

    recruitment = Recruitment.objects.filter(
        pk=recruitment_id, deleted_at__isnull=True
    ).first()
    if recruitment is None:
        raise ValidationFailed(details={"recruitment_id": "关联招募不存在或已删除"})
    return recruitment


class AnnouncementListView(PrivateAPIView):
    """公告列表查询与发布公告。"""

    query_serializer_class = AnnouncementQuerySerializer

    def get(self, request):
        """GET /api/v1/announcements：未删除公告分页列表。

        按 created_at DESC, id DESC 稳定排序；本轮不按置顶排序。

        Args:
            request: 已登录请求；可传 page、page_size。

        Returns:
            Response: HTTP 200，data 为公告分页。

        Raises:
            ValidationFailed: 分页参数无效，返回 400。
        """
        items, number, size, total = paginate(selectors.list_announcements(), request)
        data = AnnouncementSerializer(
            items, many=True, context={"request": request}
        ).data
        return page(data, number, size, total)

    def post(self, request):
        """POST /api/v1/announcements：管理员发布公告。

        Args:
            request: JSON 必填 title、content、time_kind、event_at，
                可选 link_url、recruitment_id；须为当前管理员。

        Returns:
            Response: HTTP 201，data 为公告对象。

        Raises:
            Forbidden: 非管理员，返回 403。
            ValidationError: 字段不合法，返回 400。
        """
        IsAdminFlag().has_permission(request, None)
        serializer = AnnouncementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        recruitment = _resolve_recruitment(fields.pop("recruitment_id", None))
        announcement = services.create_announcement(
            actor=request.user, recruitment=recruitment, **fields
        )
        announcement = _load_or_404(announcement.pk)
        return created(
            AnnouncementSerializer(announcement, context={"request": request}).data
        )


class AnnouncementDetailView(PrivateAPIView):
    """公告详情、编辑与本人删除。"""

    def get(self, request, announcement_id):
        """GET /api/v1/announcements/{id}：公告详情。

        Args:
            request: 已登录请求。
            announcement_id: 公告主键。

        Returns:
            Response: HTTP 200，data 为公告对象；已删除或不存在 404。
        """
        announcement = _load_or_404(announcement_id)
        return ok(AnnouncementSerializer(announcement, context={"request": request}).data)

    def patch(self, request, announcement_id):
        """PATCH /api/v1/announcements/{id}：作者（管理员）部分更新。

        Args:
            request: JSON 含至少一个可写字段；不接受 is_pinned。
            announcement_id: 公告主键。

        Returns:
            Response: HTTP 200，data 为更新后的公告对象。

        Raises:
            NotFound: 公告不存在或已删除（含更新/删除竞争），返回 404。
            Forbidden: 非管理员或非作者，返回 403。
            ValidationError: 字段不合法，返回 400。
        """
        announcement = _load_or_404(announcement_id)
        _require_author_admin(request, announcement)
        serializer = AnnouncementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        if "recruitment_id" in fields:
            fields["recruitment"] = _resolve_recruitment(fields.pop("recruitment_id"))
        services.update_announcement(announcement_id, actor=request.user, **fields)
        announcement = _load_or_404(announcement_id)
        return ok(AnnouncementSerializer(announcement, context={"request": request}).data)

    def delete(self, request, announcement_id):
        """DELETE /api/v1/announcements/{id}：作者（管理员）本人删除。

        软删除，不需要原因，不产生通知；重复删除 404 且不重复副作用。

        Args:
            request: 请求体为空或 JSON 空对象。
            announcement_id: 公告主键。

        Returns:
            Response: HTTP 200、data=None。

        Raises:
            NotFound: 公告不存在或已删除，返回 404。
            Forbidden: 非管理员或非作者，返回 403。
            ValidationError: 提供了业务字段，返回 400。
        """
        validate_data(EmptyBodySerializer, request.data)
        announcement = _load_or_404(announcement_id)
        _require_author_admin(request, announcement)
        services.soft_delete_announcement(announcement_id, actor=request.user)
        return ok()


class AnnouncementGovernanceView(PrivateAPIView):
    """管理员治理删除公告：原因必填，同事务通知作者。"""

    def delete(self, request, announcement_id):
        """DELETE /api/v1/admin/announcements/{id}：治理删除。

        Args:
            request: JSON 必填 reason（1～500 字）。
            announcement_id: 公告主键。

        Returns:
            Response: HTTP 200、data=None；软删除、审计与作者通知同事务提交。

        Raises:
            Forbidden: 非管理员，返回 403。
            NotFound: 公告不存在或已删除（重复治理删除），返回 404。
            ValidationError: 原因缺失或不合法，返回 400。
        """
        IsAdminFlag().has_permission(request, None)
        serializer = GovernanceDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _load_or_404(announcement_id)
        services.governance_delete_announcement(
            announcement_id, actor=request.user,
            reason=serializer.validated_data["reason"],
        )
        return ok()
