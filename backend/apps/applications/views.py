"""申请 HTTP 入口；写入、查询、字段裁剪分别委托对应层。"""

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
    queryset = selectors.list_applications(filters=filters, now=now, **scope)
    items, number, size, total = paginate(queryset, request)
    snapshots = [selectors.project_application(item, now) for item in items]
    data = ApplicationSummarySerializer(
        snapshots, many=True, context={"user": request.user, "now": now},
    ).data
    return page(data, number, size, total)


class ApplicationAPIView(PrivateAPIView):
    """当前申请写入口仅支持 multipart；后续 JSON 动作须显式选择解析器。"""

    parser_classes = [MultiPartParser]


class RecruitmentApplicationListView(ApplicationAPIView):
    query_serializer_class = ApplicationQuerySerializer

    def get(self, request, recruitment_id):
        now = clock.now()
        recruitment = selectors.get_publisher_recruitment(request.user, recruitment_id, now)
        return _list_response(request, self.query, now, recruitment=recruitment)

    def post(self, request, recruitment_id):
        data = validate_data(ApplicationSubmitSerializer, request.data)
        application = services.submit_application(request.user, recruitment_id, **data)
        now = clock.now()
        # 响应使用重新鉴权的快照，避免提交后并发删除使权限信息陈旧。
        application = selectors.get_application(request.user, application.pk, now)
        return created(ApplicationDetailSerializer(application, context={"user": request.user, "now": now}).data)


class MyApplicationListView(ApplicationAPIView):
    query_serializer_class = MyApplicationQuerySerializer

    def get(self, request):
        return _list_response(request, self.query, clock.now(), applicant=request.user)


class ApplicationDetailView(ApplicationAPIView):
    def get(self, request, application_id):
        now = clock.now()
        application = selectors.get_application(request.user, application_id, now)
        return ok(ApplicationDetailSerializer(application, context={"user": request.user, "now": now}).data)

    def patch(self, request, application_id):
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
        action = self.action
        data = validate_data(ApplicationActionSerializer, request.data, context={"action": action})
        application = services.perform_application_action(
            request.user, application_id, action, **data,
        )
        now = clock.now()
        return ok(ApplicationDetailSerializer(application, context={"user": request.user, "now": now}).data)
