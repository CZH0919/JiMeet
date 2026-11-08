"""业务异常与稳定错误码；HTTP 契约见 backend/design_file/api.md。"""
from rest_framework import status


class ErrorCode:
    """统一 HTTP 响应使用的稳定业务状态码。"""
    OK = "OK"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PRIVACY_NOT_CONSENTED = "PRIVACY_NOT_CONSENTED"
    SELF_APPLICATION_FORBIDDEN = "SELF_APPLICATION_FORBIDDEN"
    RECRUITMENT_NOT_OPEN = "RECRUITMENT_NOT_OPEN"
    RECRUITMENT_NOT_EDITABLE = "RECRUITMENT_NOT_EDITABLE"
    RECRUITMENT_FULL = "RECRUITMENT_FULL"
    PROCESSING_WINDOW_CLOSED = "PROCESSING_WINDOW_CLOSED"
    HEADCOUNT_BELOW_ACCEPTED = "HEADCOUNT_BELOW_ACCEPTED"
    DUPLICATE_APPLICATION = "DUPLICATE_APPLICATION"
    APPLICATION_NOT_PROCESSING = "APPLICATION_NOT_PROCESSING"
    INVALID_RESUME_FILE = "INVALID_RESUME_FILE"
    AUTH_FAILED = "AUTH_FAILED"
    SSO_UNAVAILABLE = "SSO_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # 将不支持的 HTTP 方法映射为统一错误信封。
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"


class BizError(Exception):
    """可映射到统一信封的业务异常。"""

    code = ErrorCode.INTERNAL_ERROR
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message = "服务内部错误"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        http_status: int | None = None,
        details: dict | None = None,
        audit_target: tuple[str, int | None] | None = None,
    ):
        """构造供统一异常处理器转换的业务异常。

        Args:
            message: 对外错误说明；省略或为空时使用异常类默认文案。
            code: 错误码；省略或为空时使用异常类默认值。
            http_status: HTTP 状态码；省略或为假值时使用异常类默认值。
            details: 可选的字段校验详情，不含凭据或私有文件内容。
            audit_target: 可选的 (对象类型, 主键) 审计目标，主键可为 None。
        """
        self.code = code or type(self).code
        self.http_status = http_status or type(self).http_status
        self.message = message or type(self).default_message
        self.details = details
        self.audit_target = audit_target
        super().__init__(self.message)


class NotAuthenticated(BizError):
    code = ErrorCode.UNAUTHENTICATED
    http_status = status.HTTP_401_UNAUTHORIZED
    default_message = "请先登录"


class Forbidden(BizError):
    code = ErrorCode.FORBIDDEN
    http_status = status.HTTP_403_FORBIDDEN
    default_message = "无权执行该操作"


class NotFound(BizError):
    code = ErrorCode.NOT_FOUND
    http_status = status.HTTP_404_NOT_FOUND
    default_message = "对象不存在"


class ValidationFailed(BizError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = status.HTTP_400_BAD_REQUEST
    default_message = "参数校验失败"


class Conflict(BizError):
    """409 类冲突，错误码由调用方指定。"""

    http_status = status.HTTP_409_CONFLICT
    default_message = "操作冲突"

    def __init__(self, code: str, message: str | None = None, **kwargs):
        """构造带明确业务错误码的冲突异常。

        Args:
            code: 必填的非空业务错误码。
            message: 可选错误说明，默认使用操作冲突文案。
            kwargs: 传给 BizError 的详情、审计目标等可选参数。

        Raises:
            ValueError: code 为空。
        """
        if not code:
            raise ValueError("Conflict 必须显式传入错误码")
        super().__init__(message, code=code, **kwargs)


class NotFoundAsDenied(NotFound):
    """对外表现成 404，同时由异常处理器记一条 permission_denied 审计。"""
