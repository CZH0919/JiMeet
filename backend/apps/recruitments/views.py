"""招募 HTTP 入口：校验输入、调用分层服务、返回统一信封。"""

from apps.core import clock
from apps.core.pagination import paginate
from apps.core.responses import created, ok, page
from apps.core.serializers import EmptyBodySerializer
from apps.core.views import PrivateAPIView, validate_data
from apps.recruitments import selectors, services
from apps.recruitments.serializers import (
    RecruitmentDeleteSerializer,
    RecruitmentDetailSerializer,
    RecruitmentQuerySerializer,
    RecruitmentSummarySerializer,
    RecruitmentWriteSerializer,
    TagSerializer,
)


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


class TagListView(PrivateAPIView):
    def get(self, request):
        return ok({"items": TagSerializer(selectors.list_tags(), many=True).data})


class RecruitmentListView(PrivateAPIView):
    query_serializer_class = RecruitmentQuerySerializer

    def get(self, request):
        return _list_response(request, self.query)

    def post(self, request):
        data = validate_data(RecruitmentWriteSerializer, request.data)
        recruitment = services.create_recruitment(request.user, data=data)
        return created(_detail(recruitment, request.user, clock.now()))


class MyRecruitmentListView(PrivateAPIView):
    query_serializer_class = RecruitmentQuerySerializer

    def get(self, request):
        return _list_response(request, self.query, publisher=request.user)


class RecruitmentDetailView(PrivateAPIView):
    def get(self, request, recruitment_id):
        recruitment = selectors.get_recruitment(recruitment_id)
        return ok(_detail(recruitment, request.user, clock.now()))

    def patch(self, request, recruitment_id):
        data = validate_data(RecruitmentWriteSerializer, request.data, partial=True)
        recruitment = services.update_recruitment(request.user, recruitment_id, data=data)
        return ok(_detail(recruitment, request.user, clock.now()))

    def delete(self, request, recruitment_id):
        data = validate_data(RecruitmentDeleteSerializer, request.data)
        services.delete_recruitment(request.user, recruitment_id, **data)
        return ok()


class RecruitmentCloseView(PrivateAPIView):
    def post(self, request, recruitment_id):
        validate_data(EmptyBodySerializer, request.data)
        recruitment = services.close_recruitment(request.user, recruitment_id)
        return ok(_detail(recruitment, request.user, clock.now()))
