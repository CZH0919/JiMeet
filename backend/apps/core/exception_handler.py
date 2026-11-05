"""DRF 异常 → 统一信封；拒绝类异常顺带记审计。"""
import logging

from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response

from apps.core.errors import (
    BizError,
    ErrorCode,
    Forbidden,
    NotAuthenticated,
    NotFoundAsDenied,
)
from apps.core.responses import envelope

logger = logging.getLogger(__name__)


def _stringify(detail):
    """递归将 DRF 错误详情转换为普通字符串。

    Args:
        detail: 字典、列表或单个错误详情。

    Returns:
        dict | list | str: 保留字典与列表结构的可序列化详情。
    """
    if isinstance(detail, dict):
        return {key: _stringify(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [_stringify(item) for item in detail]
    return str(detail)


def _respond(code: str, message: str, http_status: int, details=None) -> Response:
    """构造统一错误信封。

    Args:
        code: 稳定错误码。
        message: 对外错误说明。
        http_status: HTTP 状态码。
        details: 可选校验详情；有值时放入 data.details。

    Returns:
        Response: 指定 HTTP 状态的错误响应。
    """
    data = {"details": details} if details is not None else None
    return Response(envelope(code, message, data), status=http_status)


def handle(exc, context) -> Response:
    """将业务、框架或未处理异常转换为统一 HTTP 响应。

    权限拒绝尝试写审计；原始未知异常及审计失败记录到服务日志。

    Args:
        exc: 原始异常。
        context: DRF 异常上下文，包含请求和视图等信息。

    Returns:
        Response: 业务异常保留其错误码和 HTTP 状态；未知异常返回通用 500，不暴露内部详情。
    """
    if isinstance(exc, BizError):
        _audit_denial(exc, context)
        return _respond(exc.code, exc.message, exc.http_status, exc.details)

    mapped = _map_drf_exception(exc)
    if mapped is not None:
        if isinstance(exc, (exceptions.NotAuthenticated, exceptions.PermissionDenied)):
            denial = NotAuthenticated() if isinstance(exc, exceptions.NotAuthenticated) else Forbidden()
            _audit_denial(denial, context)
        code, message, http_status, details = mapped
        return _respond(code, message, http_status, details)

    logger.exception("未处理的异常", exc_info=exc)
    return _respond(
        ErrorCode.INTERNAL_ERROR,
        "服务内部错误",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _map_drf_exception(exc):
    """将 DRF 或 Django 常见异常映射为接口错误信息。

    Args:
        exc: 待映射的异常实例。

    Returns:
        tuple | None: (错误码, 文案, HTTP 状态, 详情)；不支持的异常返回 None。
    """
    if isinstance(exc, exceptions.NotAuthenticated):
        return ErrorCode.UNAUTHENTICATED, "请先登录", status.HTTP_401_UNAUTHORIZED, None
    if isinstance(exc, exceptions.AuthenticationFailed):
        return ErrorCode.AUTH_FAILED, "登录状态无效", status.HTTP_401_UNAUTHORIZED, None
    if isinstance(exc, exceptions.PermissionDenied):
        return ErrorCode.FORBIDDEN, "无权执行该操作", status.HTTP_403_FORBIDDEN, None
    if isinstance(exc, exceptions.ValidationError):
        return (
            ErrorCode.VALIDATION_ERROR,
            "参数校验失败",
            status.HTTP_400_BAD_REQUEST,
            _stringify(exc.detail),
        )
    if isinstance(exc, exceptions.ParseError):
        return ErrorCode.VALIDATION_ERROR, "请求体格式错误", status.HTTP_400_BAD_REQUEST, None
    if isinstance(exc, exceptions.MethodNotAllowed):
        return (
            ErrorCode.METHOD_NOT_ALLOWED,
            "请求方法不允许",
            status.HTTP_405_METHOD_NOT_ALLOWED,
            None,
        )
    if isinstance(exc, (exceptions.NotFound, Http404)):
        return ErrorCode.NOT_FOUND, "对象不存在", status.HTTP_404_NOT_FOUND, None
    if isinstance(exc, exceptions.APIException):
        code = (
            ErrorCode.VALIDATION_ERROR
            if 400 <= exc.status_code < 500
            else ErrorCode.INTERNAL_ERROR
        )
        return code, str(exc.detail), exc.status_code, None
    return None


def _audit_denial(exc, context) -> None:
    """为身份或权限拒绝记录审计，审计失败仅记日志。

    Args:
        exc: 业务异常；仅处理 Forbidden、NotAuthenticated、NotFoundAsDenied。
        context: DRF 异常上下文，可包含 request。
    """
    if not isinstance(exc, (Forbidden, NotAuthenticated, NotFoundAsDenied)):
        return
    request = context.get("request")
    target_type, target_id = exc.audit_target or ("request", None)
    try:
        from apps.audit.actions import PERMISSION_DENIED
        from apps.audit.service import record

        actor = getattr(request, "user", None)
        record(
            action=PERMISSION_DENIED,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target_type=target_type,
            target_id=target_id,
            reason=exc.message,
        )
    except Exception:
        logger.exception("审计记录失败")
