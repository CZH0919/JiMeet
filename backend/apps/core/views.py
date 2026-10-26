"""业务 API 的严格查询参数校验与私有响应缓存策略。"""

from rest_framework.parsers import JSONParser
from rest_framework.views import APIView

from apps.core.serializers import EmptyQuerySerializer


def validate_data(serializer_class, data, **kwargs):
    """返回通过白名单及字段校验的输入，失败交由公共异常处理器转换。"""
    serializer = serializer_class(data=data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class PrivateAPIView(APIView):
    """沿用默认 Session/CSRF 鉴权，所有响应（含拒绝）禁止共享或持久缓存。"""

    parser_classes = [JSONParser]
    query_serializer_class = EmptyQuerySerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        serializer_class = self.query_serializer_class if request.method in {"GET", "HEAD"} else EmptyQuerySerializer
        self.query = validate_data(serializer_class, request.query_params)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
