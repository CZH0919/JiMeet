import logging
import re
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-Id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return _request_id.get()


class RequestIdMiddleware:
    """
    从 X-Request-Id 取值（不合法则生成），写入 request、日志上下文与响应头。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
        record.request_id = current_request_id()
        return True
