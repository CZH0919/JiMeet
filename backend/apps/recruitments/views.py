"""招募的 HTTP 入口，完整请求与字段契约见 backend/design_file/api.md。

需认证的入口先检查会话和 CSRF，分别拒绝为 401 和 403；非法查询或请求数据通常返回 400，不支持的媒体类型返回 415。异常由统一处理器转换为错误信封；简历下载成功直接返回文件流。
"""

from apps.core import clock
from apps.core.pagination import paginate
from apps.core.permissions import IsAdminFlag
from apps.core.responses import created, ok, page
from apps.core.serializers import EmptyBodySerializer
from apps.core.views import PrivateAPIView, validate_data
from apps.recruitments import selectors, services
from apps.recruitments.serializers import (
    RecruitmentDeleteSerializer,
    RecruitmentGovernanceSerializer,
    RecruitmentDetailSerializer,
    RecruitmentQuerySerializer,
    RecruitmentSummarySerializer,
    RecruitmentWriteSerializer,
    TagSerializer,
)


def _detail(recruitment, user, now):
    """按当前用户和时间生成招募详情数据。

    Args:
        recruitment: 已获取的招募对象。
        user: 当前已认证用户。
        now: 状态与权限判断时间。

    Returns:
        dict: RecruitmentDetailSerializer 的输出，含当前用户权限和经裁剪的申请信息。
    """
    projected = selectors.project_recruitment(recruitment, now)
    context = selectors.detail_context(projected, user, now)
    return RecruitmentDetailSerializer(projected, context=context).data


def _list_response(request, filters, *, publisher=None):
    """执行招募列表查询、分页和时间投影。

    Args:
        request: 带分页参数的 DRF 请求。
        filters: 已校验的筛选条件。
        publisher: 可选发布者范围，默认不限定。

    Returns:
        Response: HTTP 200，data 为招募摘要分页对象。

    Raises:
        ValidationFailed: 分页参数不合法，返回 400。
    """
    now = clock.now()
    queryset = selectors.list_recruitments(filters=filters, now=now, publisher=publisher)
    items, number, size, total = paginate(queryset, request)
    snapshots = [selectors.project_recruitment(item, now) for item in items]
    return page(RecruitmentSummarySerializer(snapshots, many=True).data, number, size, total)


class TagListView(PrivateAPIView):
    def get(self, request):
        """GET /api/v1/tags：读取启用的领域标签。

        Args:
            request: 已认证请求，不接受查询参数。

        Returns:
            Response: HTTP 200，data.items 为按展示顺序排列的 id/name 标签列表。
        """
        return ok({"items": TagSerializer(selectors.list_tags(), many=True).data})


class RecruitmentListView(PrivateAPIView):
    query_serializer_class = RecruitmentQuerySerializer

    def get(self, request):
        """GET /api/v1/recruitments：浏览未删除招募。

        Args:
            request: 已认证请求；可按 q、type、tag、status 筛选，使用 page/page_size 分页。

        Returns:
            Response: HTTP 200，data 含 items、page、page_size、total；开放招募优先，查询不写回到期状态。

        Raises:
            ValidationFailed: 分页参数无效，返回 400。
        """
        return _list_response(request, self.query)

    def post(self, request):
        """POST /api/v1/recruitments：发布招募。

        Args:
            request: JSON 必填 title、type、description、max_headcount、deadline、tag_ids，可选 min_headcount。

        Returns:
            Response: HTTP 201，data 为包含当前权限的招募详情。

        Raises:
            ValidationError: 请求字段不符合 RecruitmentWriteSerializer，返回 400。
            ValidationFailed: 时间、人数或标签不合法，返回 400。
        """
        data = validate_data(RecruitmentWriteSerializer, request.data)
        recruitment = services.create_recruitment(request.user, data=data)
        return created(_detail(recruitment, request.user, clock.now()))


class MyRecruitmentListView(PrivateAPIView):
    query_serializer_class = RecruitmentQuerySerializer

    def get(self, request):
        """GET /api/v1/me/recruitments：查询本人发布的未删除招募。

        Args:
            request: 已认证请求；可按 q、type、tag、status 筛选，使用 page/page_size 分页。

        Returns:
            Response: HTTP 200，返回与公共招募列表结构一致的分页摘要，包括关闭和满员记录。

        Raises:
            ValidationFailed: 分页参数无效，返回 400。
        """
        return _list_response(request, self.query, publisher=request.user)


class RecruitmentDetailView(PrivateAPIView):
    def get(self, request, recruitment_id):
        """GET /api/v1/recruitments/{id}：读取招募详情。

        Args:
            request: 已认证请求，不接受查询参数。
            recruitment_id: 路径中的招募主键。

        Returns:
            Response: HTTP 200，data 含详情、本人申请摘要及操作权限；仅发布者获得申请状态计数。

        Raises:
            NotFound: 招募不存在或已删除，返回 404。
        """
        recruitment = selectors.get_recruitment(recruitment_id)
        return ok(_detail(recruitment, request.user, clock.now()))

    def patch(self, request, recruitment_id):
        """PATCH /api/v1/recruitments/{id}：由发布者修改招募。

        Args:
            request: JSON 至少提供一个可写字段；字段集合与发布接口一致，不接受 URL 查询参数。
            recruitment_id: 路径中的招募主键。

        Returns:
            Response: HTTP 200，data 为最新时间投影下的招募详情。

        Raises:
            ValidationError: 请求字段不合法或为空，返回 400。
            BizError: 非法业务参数 400、非发布者 403、对象不可见 404，或编辑窗口/人数冲突 409。
        """
        data = validate_data(RecruitmentWriteSerializer, request.data, partial=True)
        recruitment = services.update_recruitment(request.user, recruitment_id, data=data)
        return ok(_detail(recruitment, request.user, clock.now()))

    def delete(self, request, recruitment_id):
        """DELETE /api/v1/recruitments/{id}：软删除招募。

        Args:
            request: JSON 可含 reason；仅本人删除，管理员标记不绕过发布者及状态限制。删除不物理清理申请或简历。
            recruitment_id: 路径中的招募主键。

        Returns:
            Response: HTTP 200、data=None。

        Raises:
            ValidationError: 删除字段不合法，返回 400。
            BizError: 越权 403、对象不可见/已删除 404，或发布者窗口不允许 409。
        """
        data = validate_data(RecruitmentDeleteSerializer, request.data)
        services.delete_recruitment(request.user, recruitment_id, **data)
        return ok()


class RecruitmentCloseView(PrivateAPIView):
    def post(self, request, recruitment_id):
        """POST /api/v1/recruitments/{id}/close：手动关闭招募。

        Args:
            request: 已认证发布者的写请求，请求体为空或 JSON 空对象。
            recruitment_id: 路径中的招募主键。

        Returns:
            Response: HTTP 200，data 为已关闭的招募详情；已有申请仍有七天处理窗口。

        Raises:
            ValidationError: 包含未声明业务字段，返回 400。
            BizError: 非发布者 403、对象不可见 404 或无法重复关闭等窗口冲突 409。
        """
        validate_data(EmptyBodySerializer, request.data)
        recruitment = services.close_recruitment(request.user, recruitment_id)
        return ok(_detail(recruitment, request.user, clock.now()))


class RecruitmentGovernanceView(PrivateAPIView):
    """治理删除招聘的独立管理员入口。"""

    def delete(self, request, recruitment_id):
        """DELETE /api/v1/admin/recruitments/{id}：按治理权限删除招聘。

        Args:
            request: 已认证管理员请求，JSON 必须提供 1～500 字的 reason。
            recruitment_id: 目标招聘主键。

        Returns:
            Response: HTTP 200、data=None，通知发布者及本次失效申请人。

        Raises:
            BizError: 无权限 403、对象不存在/已删除 404、原因无效 400。
        """
        IsAdminFlag().has_permission(request, None)
        data = validate_data(RecruitmentGovernanceSerializer, request.data)
        services.governance_delete_recruitment(request.user, recruitment_id, **data)
        return ok()
