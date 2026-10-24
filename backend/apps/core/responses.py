from rest_framework.response import Response

from apps.core.errors import ErrorCode
from apps.core.middleware import current_request_id


def envelope(code: str, message: str = "", data=None, request_id: str | None = None) -> dict:
    """
    创建统一响应信封。

    Args:
        code: 错误码，参考 ErrorCode
        message: 错误信息，通常为字符串
        data: 响应数据，通常为字典或列表
        request_id: 可选的请求 ID，若未提供则使用当前请求的 request

    Returns:
        dict: 包含 code、message、data 和 request_id 的响应字典
    
    """
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
    """
    创建分页响应。

    Args:
        items: 当前页的结果列表
        page_number: 当前页码，从 1 开始
        page_size: 每页的结果数量
        total: 总结果数量

    Returns:
        Response: 包含分页信息的响应对象，数据结构如下：
        ```
            "items": [...],  # 当前页的结果列表
            "page": page_number,  # 当前页码
            "page_size": page_size,  # 每页的结果数量
            "total": total,  # 总结果数量
        ```
    
    """
    return ok(
        {
            "items": items,
            "page": page_number,
            "page_size": page_size,
            "total": total,
        }
    )
