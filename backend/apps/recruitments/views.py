"""招募 HTTP 入口：校验输入、调用分层服务、返回统一信封。"""

from rest_framework.parsers import JSONParser
from rest_framework.views import APIView

from apps.core import clock
from apps.core.pagination import paginate
from apps.core.responses import created, ok, page
from apps.core.serializers import EmptyBodySerializer, EmptyQuerySerializer
from apps.recruitments import selectors, services
from apps.recruitments.serializers import (
    RecruitmentDeleteSerializer,
    RecruitmentDetailSerializer,
    RecruitmentQuerySerializer,
    RecruitmentSummarySerializer,
    RecruitmentWriteSerializer,
    TagSerializer,
)


def _validated(serializer_class, data, **kwargs):
    serializer = serializer_class(data=data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _detail(recruitment, user, now):
    projected = selectors.project_recruitment(recruitment, now)
    context = selectors.detail_context(projected, user, now)
    return RecruitmentDetailSerializer(projected, context=context).data


def _list_response(request, filters, *, publisher=None):
    now = clock.now()
    queryset = selectors.list_recruitments(filters=filters, now=now, publisher=publisher)
    items, number, size, total = paginate(queryset, request)
    snapshots = [selectors.project_recruitment(item, now) for item in items]
    return page(RecruitmentSummarySerializer(snapshots, many=True).data, number, size, total)


class RecruitmentAPIView(APIView):
    """沿用默认 Session/CSRF 鉴权，统一拒绝未声明的查询参数。"""

    parser_classes = [JSONParser]
    query_serializer_class = EmptyQuerySerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        serializer_class = self.query_serializer_class if request.method in {"GET", "HEAD"} else EmptyQuerySerializer
        self.query = _validated(serializer_class, request.query_params)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class TagListView(RecruitmentAPIView):
    def get(self, request):
        return ok({"items": TagSerializer(selectors.list_tags(), many=True).data})


class RecruitmentListView(RecruitmentAPIView):
    query_serializer_class = RecruitmentQuerySerializer

    def get(self, request):
        return _list_response(request, self.query)

    def post(self, request):
        data = _validated(RecruitmentWriteSerializer, request.data)
        recruitment = services.create_recruitment(request.user, data=data)
        return created(_detail(recruitment, request.user, clock.now()))


class MyRecruitmentListView(RecruitmentAPIView):
    query_serializer_class = RecruitmentQuerySerializer

    def get(self, request):
        return _list_response(request, self.query, publisher=request.user)


class RecruitmentDetailView(RecruitmentAPIView):
    def get(self, request, recruitment_id):
        recruitment = selectors.get_recruitment(recruitment_id)
        return ok(_detail(recruitment, request.user, clock.now()))

    def patch(self, request, recruitment_id):
        data = _validated(RecruitmentWriteSerializer, request.data, partial=True)
        recruitment = services.update_recruitment(request.user, recruitment_id, data=data)
        return ok(_detail(recruitment, request.user, clock.now()))

    def delete(self, request, recruitment_id):
        data = _validated(RecruitmentDeleteSerializer, request.data)
        services.delete_recruitment(request.user, recruitment_id, **data)
        return ok()


class RecruitmentCloseView(RecruitmentAPIView):
    def post(self, request, recruitment_id):
        _validated(EmptyBodySerializer, request.data)
        recruitment = services.close_recruitment(request.user, recruitment_id)
        return ok(_detail(recruitment, request.user, clock.now()))
