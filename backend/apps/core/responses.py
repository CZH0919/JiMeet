"""统一响应信封，见 implementation_plan.md 6.1。"""
from rest_framework.response import Response

from apps.core.errors import ErrorCode
from apps.core.middleware import current_request_id


def envelope(code: str, message: str = "", data=None, request_id: str | None = None) -> dict:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id or current_request_id(),
    }


def ok(data=None, *, status: int = 200) -> Response:
    return Response(envelope(ErrorCode.OK, "", data), status=status)


def created(data) -> Response:
    return Response(envelope(ErrorCode.OK, "", data), status=201)


def page(items, page_number: int, page_size: int, total: int) -> Response:
    return ok(
        {
            "items": items,
            "page": page_number,
            "page_size": page_size,
            "total": total,
        }
    )
