"""账号接口：解析参数、调用服务并返回统一信封。"""
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import DevLoginSerializer, ProfileUpdateSerializer, profile_data
from apps.accounts.services import give_privacy_consent, update_profile
from apps.accounts.sso import DevSSOProvider
from apps.core.errors import ErrorCode, NotFound
from apps.core.responses import envelope, ok


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """公开的 CSRF token 获取入口。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """设置 cookie 并返回可用于请求头的 masked token。"""
        return ok({"csrf_token": get_token(request._request)})


class DevLoginView(APIView):
    """开发登录需同时满足配置开关与 CSRF 验证。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """验证开发参数后通过认证 backend 建立会话。"""
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
        """清除 session，后续访问本人资料须重新登录。"""
        logout(request._request)
        return ok()


class MeView(APIView):
    """当前用户资料读取与更新。"""

    def get(self, request):
        """返回仅本人可见的资料字段。"""
        return ok(profile_data(request.user))

    def patch(self, request):
        """校验字段白名单后更新昵称与邮件开关。"""
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = update_profile(request.user, **serializer.validated_data)
        return ok(profile_data(user))


class PrivacyConsentView(APIView):
    """个人信息处理告知确认入口。"""

    def post(self, request):
        """首次确认时间写入后保持不变。"""
        return ok(profile_data(give_privacy_consent(request.user)))


class SSOReservedView(APIView):
    """正式 SSO 跳转及回调本周均返回预留响应。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """用统一错误信封明确返回未实现状态。"""
        return Response(envelope(ErrorCode.INTERNAL_ERROR, "预留"), status=501)
