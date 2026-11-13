"""账号与开发会话的 HTTP 入口，完整请求与字段契约见 backend/design_file/api.md。

需认证的入口先检查会话和 CSRF，分别拒绝为 401 和 403；非法查询或请求数据通常返回 400，不支持的媒体类型返回 415。异常由统一处理器转换为错误信封；简历下载成功直接返回文件流。
"""
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    DevLoginSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    profile_data,
)
from apps.accounts.services import (
    PASSWORD_BACKEND,
    give_privacy_consent,
    login_with_password,
    register_with_password,
    update_profile,
)
from apps.accounts.sso import DevSSOProvider
from apps.core.errors import ErrorCode, NotFound
from apps.core.responses import created, envelope, ok
from apps.core.views import PrivateAPIView


def _client_ip(request) -> str:
    """取请求来源 IP 供失败限流计数。

    Args:
        request: DRF 请求。

    Returns:
        str: REMOTE_ADDR；缺失时为空字符串（对应键不计数）。
    """
    return (request._request.META.get("REMOTE_ADDR") or "").strip()


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """公开的 CSRF token 获取入口。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """GET /api/v1/auth/csrf：获取 CSRF 令牌。

        Args:
            request: 公开请求，可在登录前调用。

        Returns:
            Response: HTTP 200，data.csrf_token 为可放入请求头的令牌，同时设置 CSRF Cookie。
        """
        return ok({"csrf_token": get_token(request._request)})


class RegisterView(APIView):
    """邮箱密码注册公开入口；匿名请求强制 CSRF。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """POST /api/v1/auth/register：注册普通账号并建立会话。

        Args:
            request: JSON 必填 email、password、name，可选 nickname、role；
                匿名请求必须提供匹配的 CSRF Cookie 与令牌。

        Returns:
            Response: HTTP 201，data 为本人资料；建立 Session 并轮换 CSRF 令牌，
                响应禁止缓存。

        Raises:
            PermissionDenied: CSRF 校验失败，返回 403。
            ValidationError: 输入字段不合法，返回 400。
            ValidationFailed: 邮箱冲突或密码不合规，返回 400。
            BizError: 失败限流，返回 429 RATE_LIMITED。
        """
        SessionAuthentication().enforce_csrf(request)
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_with_password(ip=_client_ip(request), **serializer.validated_data)
        login(request._request, user, backend=PASSWORD_BACKEND)
        response = created(profile_data(user))
        response["Cache-Control"] = "private, no-store"
        return response


class LoginView(APIView):
    """邮箱密码登录公开入口；匿名请求强制 CSRF。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """POST /api/v1/auth/login：凭邮箱密码建立会话。

        不存在邮箱、错误或不可用密码统一 401，不泄露账号是否存在；
        凭据正确但账号停用返回 403。

        Args:
            request: JSON 必填 email、password；匿名请求也须通过 CSRF 校验。

        Returns:
            Response: HTTP 200，data 为本人资料；建立 Session 并轮换 CSRF 令牌，
                响应禁止缓存。

        Raises:
            PermissionDenied: CSRF 校验失败，返回 403。
            ValidationError: 输入字段不合法，返回 400。
            BizError: 凭据不合法 401 AUTH_FAILED；失败限流 429 RATE_LIMITED。
            Forbidden: 账号已停用，返回 403。
        """
        SessionAuthentication().enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = login_with_password(ip=_client_ip(request), **serializer.validated_data)
        login(request._request, user)
        response = ok(profile_data(user))
        response["Cache-Control"] = "private, no-store"
        return response


class DevLoginView(APIView):
    """开发登录需同时满足配置开关与 CSRF 验证。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """POST /api/v1/auth/dev-login：建立开发身份会话。

        同一编号复用账号；新编号创建开发身份，不代表正式注册或学校 SSO 已实现。

        Args:
            request: JSON 必填 real_id，可选 name、email；匿名请求也必须提供匹配的 CSRF Cookie 与令牌。

        Returns:
            Response: HTTP 200，data 为本人资料；建立 Session 并轮换 CSRF 令牌。

        Raises:
            NotFound: DEBUG 或 ALLOW_DEV_LOGIN 未启用，返回 404。
            PermissionDenied: CSRF 校验失败，返回 403。
            ValidationError: 输入字段不合法，返回 400。
            BizError: 身份冲突返回 401 AUTH_FAILED，停用账号返回 403。
        """
        # 路由之外再次校验，避免运行期配置改变后入口仍可使用。
        if not (settings.DEBUG and settings.ALLOW_DEV_LOGIN):
            raise NotFound()
        # 匿名登录不会触发 SessionAuthentication 的默认 CSRF 检查，显式补上。
        SessionAuthentication().enforce_csrf(request)
        serializer = DevLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identity = DevSSOProvider().exchange(serializer.validated_data)
        user = authenticate(request=request._request, identity=identity)
        login(request._request, user)
        return ok(profile_data(user))


class LogoutView(APIView):
    """结束当前已认证会话。"""

    def post(self, request):
        """POST /api/v1/auth/logout：注销当前会话。

        Args:
            request: 已认证且通过 CSRF 的请求，不要求业务字段。

        Returns:
            Response: HTTP 200、data=None；原会话不再可用于访问本人资料。
        """
        logout(request._request)
        return ok()


class MeView(PrivateAPIView):
    """当前用户资料读取与更新。"""

    def get(self, request):
        """GET /api/v1/me：读取本人资料。

        Args:
            request: 已认证请求，不接受 URL 查询参数。

        Returns:
            Response: HTTP 200，data 为 profile_data 定义的本人资料，包含姓名、邮箱和隐私确认状态。
        """
        return ok(profile_data(request.user))

    def patch(self, request):
        """PATCH /api/v1/me：修改本人昵称或邮件通知偏好。

        Args:
            request: JSON 可含 nickname、email_notify_enabled，不接受 URL 查询参数；空对象表示不修改。

        Returns:
            Response: HTTP 200，data 为修改后的本人资料，响应禁止缓存。

        Raises:
            ValidationError: 未知/只读字段或字段值不合格，返回 400。
            ValidationFailed: 账号服务拒绝昵称或通知开关，返回 400。
        """
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = update_profile(request.user, **serializer.validated_data)
        return ok(profile_data(user))


class PrivacyConsentView(APIView):
    """个人信息处理告知确认入口。"""

    def post(self, request):
        """POST /api/v1/me/privacy-consent：确认隐私告知。

        Args:
            request: 已认证且通过 CSRF 的请求，不要求业务字段。

        Returns:
            Response: HTTP 200，data 为 privacy_consented=True 的本人资料；重复确认不刷新首次时间。
        """
        return ok(profile_data(give_privacy_consent(request.user)))


class SSOReservedView(APIView):
    """正式 SSO 登录及回调占位接口，当前均返回 HTTP 501。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """GET /api/v1/auth/sso/login、GET /api/v1/auth/sso/callback：返回正式认证占位响应。

        Args:
            request: 公开请求，当前不交换票据或建立会话。

        Returns:
            Response: HTTP 501、code=INTERNAL_ERROR、message=预留、data=None。
        """
        return Response(envelope(ErrorCode.INTERNAL_ERROR, "预留"), status=501)
