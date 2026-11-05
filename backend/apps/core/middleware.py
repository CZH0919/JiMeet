import logging
import re
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-Id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    """读取当前请求上下文中的追踪标识。

    Returns:
        str: 请求标识；没有请求上下文时为 "-"。
    """
    return _request_id.get()


class RequestIdMiddleware:
    """
    从 X-Request-Id 取值（不合法则生成），写入 request、日志上下文与响应头。
    """

    def __init__(self, get_response):
        """保存下游请求处理入口。

        Args:
            get_response: 接收 Django 请求并返回响应的可调用对象。
        """
        self.get_response = get_response

    def __call__(self, request):
        """设置请求与日志追踪标识，并在请求结束时恢复上下文。

        无效或缺失的标识替换为随机值；下游异常继续向上传播，日志上下文仍会恢复。

        Args:
            request: Django 请求；X-Request-Id 允许 1～64 位字母、数字或连字符。

        Returns:
            HttpResponse: 下游响应，附带实际使用的 X-Request-Id 响应头。
        """
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        token = _request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


class RequestIdLogFilter(logging.Filter):
    def filter(self, record):
        """为日志记录附加当前请求标识。

        Args:
            record: logging.LogRecord 实例。

        Returns:
            bool: 始终为 True，不过滤日志。
        """
        record.request_id = current_request_id()
        return True
