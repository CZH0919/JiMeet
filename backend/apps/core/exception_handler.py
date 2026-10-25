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
    if isinstance(detail, dict):
        return {key: _stringify(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [_stringify(item) for item in detail]
    return str(detail)


def _respond(code: str, message: str, http_status: int, details=None) -> Response:
    data = {"details": details} if details is not None else None
    return Response(envelope(code, message, data), status=http_status)


def handle(exc, context) -> Response:
    """
    处理 DRF 异常，返回统一信封格式的响应，并在拒绝类异常时记录审计日志。

    Args:
        exc: 异常对象
        context: 上下文字典，通常包含 'request' 键
    Returns:
        DRF Response 对象，包含统一信封格式的响应数据
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
