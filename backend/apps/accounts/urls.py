"""
账号路由，开发登录仅在两个开关同时启用时注册。

urlpatterns：
    path("auth/csrf", views.CsrfView.as_view(), name="auth-csrf"),
        获取 CSRF token，前端在登录前必须先调用此接口。
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
        注销登录，清除会话。
    path("auth/sso/login", views.SSOReservedView.as_view(), name="auth-sso-login"),
        预留正式认证跳转，开发期不使用。
    path("auth/sso/callback", views.SSOReservedView.as_view(), name="auth-sso-callback"),
        预留正式认证回调，开发期不使用。
    path("me", views.MeView.as_view(), name="me"),
        获取本人可见资料，需登录。
    path("me/privacy-consent", views.PrivacyConsentView.as_view(), name="privacy-consent"),
        确认隐私协议，需登录。
    path("auth/dev-login", views.DevLoginView.as_view(), name="auth-dev-login"),
        开发登录，仅在 DEBUG 与 ALLOW_DEV_LOGIN 同时启用时注册。

"""
from django.conf import settings
from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("auth/csrf", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/sso/login", views.SSOReservedView.as_view(), name="auth-sso-login"),
    path("auth/sso/callback", views.SSOReservedView.as_view(), name="auth-sso-callback"),
    path("me", views.MeView.as_view(), name="me"),
    path("me/privacy-consent", views.PrivacyConsentView.as_view(), name="privacy-consent"),
]

if settings.DEBUG and settings.ALLOW_DEV_LOGIN:
    urlpatterns.append(path("auth/dev-login", views.DevLoginView.as_view(), name="auth-dev-login"))
