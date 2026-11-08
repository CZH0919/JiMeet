from rest_framework.response import Response

from apps.core.errors import ErrorCode
from apps.core.middleware import current_request_id


def envelope(code: str, message: str = "", data=None, request_id: str | None = None) -> dict:
    """构造统一响应信封，不执行 JSON 渲染。

    Args:
        code: 稳定的业务状态码，成功使用 ErrorCode.OK。
        message: 对外提示，默认空字符串。
        data: 已准备的响应数据，默认 None。
        request_id: 可选请求标识；未提供或为空时读取当前请求上下文。

    Returns:
        dict: 包含 code、message、data、request_id 的字典。
    """
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id or current_request_id(),
    }


def ok(data=None, *, status: int = 200) -> Response:
    """创建带统一成功信封的响应。

    Args:
        data: 已序列化的业务数据，默认 None。
        status: HTTP 状态码，默认 200。

    Returns:
        Response: code 为 OK 的 DRF 响应。
    """
    return Response(envelope(ErrorCode.OK, "", data), status=status)


def created(data) -> Response:
    """创建资源新增成功的响应。

    Args:
        data: 已序列化的新资源数据。

    Returns:
        Response: HTTP 201，code 为 OK。
    """
    return Response(envelope(ErrorCode.OK, "", data), status=201)


def page(items, page_number: int, page_size: int, total: int) -> Response:
    """创建统一的分页成功响应。

    Args:
        items: 当前页已序列化的记录列表。
        page_number: 从 1 开始的页码。
        page_size: 每页记录数。
        total: 过滤后、分页前的记录总数。

    Returns:
        Response: HTTP 200，data 包含 items、page、page_size、total。
    """
    return ok(
        {
            "items": items,
            "page": page_number,
            "page_size": page_size,
            "total": total,
        }
    )
