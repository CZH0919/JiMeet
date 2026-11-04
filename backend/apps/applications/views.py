"""申请的 HTTP 入口，完整请求与字段契约见 backend/design_file/api.md。

需认证的入口先检查会话和 CSRF，分别拒绝为 401 和 403；非法查询或请求数据通常返回 400，不支持的媒体类型返回 415。异常由统一处理器转换为错误信封；简历下载成功直接返回文件流。
"""

from rest_framework.parsers import MultiPartParser

from apps.applications import selectors, services
from apps.applications.serializers import (
    ApplicationActionSerializer,
    ApplicationDetailSerializer,
    ApplicationQuerySerializer,
    ApplicationSubmitSerializer,
    ApplicationSummarySerializer,
    ApplicationUpdateSerializer,
    MyApplicationQuerySerializer,
)
from apps.core import clock
from apps.core.pagination import paginate
from apps.core.responses import created, ok, page
from apps.core.views import PrivateAPIView, validate_data


def _list_response(request, filters, now, **scope):
    """查询并分页输出经权限裁剪的申请摘要。

    Args:
        request: 当前 DRF 请求。
        filters: 已校验的状态等过滤条件。
        now: 统一业务时间。
        scope: applicant 或已鉴权 recruitment，必须且只能提供一项。

    Returns:
        Response: HTTP 200，data 为申请摘要分页对象。

    Raises:
        ValidationFailed: 分页参数不合法。
        ValueError: 调用方提供的查询范围不合法。
    """
    queryset = selectors.list_applications(filters=filters, now=now, **scope)
    items, number, size, total = paginate(queryset, request)
    snapshots = [selectors.project_application(item, now) for item in items]
    data = ApplicationSummarySerializer(
        snapshots, many=True, context={"user": request.user, "now": now},
    ).data
    return page(data, number, size, total)


class ApplicationAPIView(PrivateAPIView):
    """申请查询及 multipart 投递/修改基类；JSON 动作使用独立动作视图。"""

    parser_classes = [MultiPartParser]


class RecruitmentApplicationListView(ApplicationAPIView):
    query_serializer_class = ApplicationQuerySerializer

    def get(self, request, recruitment_id):
        """GET /api/v1/recruitments/{id}/applications：发布者读取申请列表。

        Args:
            request: 已认证请求；可传单一 status 及 page/page_size。
            recruitment_id: 路径中的招募主键。

        Returns:
            Response: HTTP 200，data 为 ApplicationSummary 分页；留存期内包含已删除招募的受限历史。

        Raises:
            BizError: 不是发布者、对象不存在或留存到期时 404；非法分页时 400。
        """
        now = clock.now()
        recruitment = selectors.get_publisher_recruitment(request.user, recruitment_id, now)
        return _list_response(request, self.query, now, recruitment=recruitment)

    def post(self, request, recruitment_id):
        """POST /api/v1/recruitments/{id}/applications：提交招募申请。

        Args:
            request: multipart 必填单个 resume，可选 note；不接受额外字段、多份同名文件或 URL 查询参数。
            recruitment_id: 路径中的招募主键。

        Returns:
            Response: HTTP 201，data 为提交后重新鉴权的 ApplicationDetail。

        Raises:
            ValidationError: 缺失字段、重复字段或未知字段，返回 400。
            BizError: 简历不合法 400、本人投递/隐私未确认 403、对象不可见 404，或窗口关闭/重复申请 409。
        """
        data = validate_data(ApplicationSubmitSerializer, request.data)
        application = services.submit_application(request.user, recruitment_id, **data)
        now = clock.now()
        # 响应使用重新鉴权的快照，避免提交后并发删除使权限信息陈旧。
        application = selectors.get_application(request.user, application.pk, now)
        return created(ApplicationDetailSerializer(application, context={"user": request.user, "now": now}).data)


class MyApplicationListView(ApplicationAPIView):
    query_serializer_class = MyApplicationQuerySerializer

    def get(self, request):
        """GET /api/v1/me/applications：查询本人的申请历史。

        Args:
            request: 已认证请求；可按 status、recruitment_id 筛选，使用 page/page_size 分页。

        Returns:
            Response: HTTP 200，data 为申请摘要分页；包含撤回记录，留存到期记录在分页前排除。

        Raises:
            ValidationFailed: 分页参数不合法，返回 400。
        """
        return _list_response(request, self.query, clock.now(), applicant=request.user)


class ApplicationDetailView(ApplicationAPIView):
    def get(self, request, application_id):
        """GET /api/v1/applications/{id}：读取本人或所发布招募的申请详情。

        Args:
            request: 已认证请求，不接受查询参数；管理员身份不增加读取权限。
            application_id: 路径中的申请主键。

        Returns:
            Response: HTTP 200，data 为按关系裁剪的 ApplicationDetail；读取不清除发布者未读修改标记。

        Raises:
            BizError: 申请不存在、无业务关系或留存到期时返回 404。
        """
        now = clock.now()
        application = selectors.get_application(request.user, application_id, now)
        return ok(ApplicationDetailSerializer(application, context={"user": request.user, "now": now}).data)

    def patch(self, request, application_id):
        """PATCH /api/v1/applications/{id}：修改本人处理中申请。

        Args:
            request: multipart 至少提供 note 或 resume；空说明表示清空，简历替换遵守上传校验规则。
            application_id: 路径中的申请主键。

        Returns:
            Response: HTTP 200，data 为最新申请详情，并为发布者标记未读修改。

        Raises:
            ValidationError: 修改字段为空、未知或重复，返回 400。
            BizError: 简历无效 400、非申请人 403、对象不可见 404，或状态不允许修改 409。
        """
        data = validate_data(ApplicationUpdateSerializer, request.data)
        application = services.modify_application(
            request.user, application_id,
            note=data.get("note"), update_note="note" in data, resume=data.get("resume"),
        )
        now = clock.now()
        return ok(ApplicationDetailSerializer(application, context={"user": request.user, "now": now}).data)


class ApplicationActionView(PrivateAPIView):
    action = None

    def post(self, request, application_id):
        """POST /api/v1/applications/{id}/{action}：执行申请动作。

        动作包括 withdraw、accept、reject、hold、unhold、read。read 使用最近读取的 updated_at，版本已过期时保留未读标记并返回当前详情；
        hold/unhold 支持幂等。

        Args:
            request: JSON；仅 read 必须提供带时区的 seen_updated_at，其余动作请求体为空或空对象。action 由路由指定。
            application_id: 路径中的申请主键。

        Returns:
            Response: HTTP 200，data 为动作后的 ApplicationDetail。

        Raises:
            ValidationError: 动作字段或版本时间不合法，返回 400。
            BizError: 身份不符 403、对象不可见 404，或终态/处理窗口冲突 409。
        """
        action = self.action
        data = validate_data(ApplicationActionSerializer, request.data, context={"action": action})
        application = services.perform_application_action(
            request.user, application_id, action, **data,
        )
        now = clock.now()
        return ok(ApplicationDetailSerializer(application, context={"user": request.user, "now": now}).data)
