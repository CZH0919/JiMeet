"""业务 API 的严格查询参数校验与私有响应缓存策略。"""

from rest_framework.parsers import JSONParser
from rest_framework.views import APIView

from apps.core.serializers import EmptyQuerySerializer


def validate_data(serializer_class, data, **kwargs):
    """使用指定序列化器校验输入并返回规范化数据。

    Args:
        serializer_class: DRF 序列化器类。
        data: 请求体或查询参数。
        kwargs: 传给序列化器的 partial、context 等参数。

    Returns:
        dict: 序列化器的 validated_data。

    Raises:
        ValidationError: 输入不符合该序列化器声明的契约，统一映射为 HTTP 400。
    """
    serializer = serializer_class(data=data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class PrivateAPIView(APIView):
    """沿用默认 Session/CSRF 鉴权，所有响应（含拒绝）禁止共享或持久缓存。"""

    parser_classes = [JSONParser]
    query_serializer_class = EmptyQuerySerializer

    def initial(self, request, *args, **kwargs):
        """完成认证与权限检查后，校验查询参数。

        Args:
            request: DRF 请求；GET/HEAD 使用视图查询序列化器，写请求不接受查询参数。
            args: DRF 传入的位置路由参数。
            kwargs: DRF 传入的命名路由参数。

        Raises:
            ValidationError: 查询键未知、重复或取值无效。
            BizError: 继承的业务权限检查拒绝访问。
            APIException: DRF 认证、CSRF 或请求协商失败。
        """
        super().initial(request, *args, **kwargs)
        serializer_class = self.query_serializer_class if request.method in {"GET", "HEAD"} else EmptyQuerySerializer
        self.query = validate_data(serializer_class, request.query_params)

    def finalize_response(self, request, response, *args, **kwargs):
        """完成 DRF 响应处理并禁止缓存私有接口响应。

        Args:
            request: 当前 DRF 请求。
            response: 视图或异常处理器产生的响应。
            args: DRF 传入的位置参数。
            kwargs: DRF 传入的命名参数。

        Returns:
            Response | HttpResponse: 带有 Cache-Control: private, no-store 的响应，含错误响应。
        """
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
