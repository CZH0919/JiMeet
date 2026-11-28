"""账号路由；开发登录只供本地开发或受访问保护的独立测试环境使用。"""
from django.urls import path

from apps.accounts import views
from apps.accounts.login_policy import development_login_enabled

urlpatterns = [
    path("auth/csrf", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/register/send-code", views.RegistrationCodeView.as_view(), name="auth-register-send-code"),
    path("auth/register/verify-code", views.VerifyRegistrationCodeView.as_view(), name="auth-register-verify-code"),
    path("auth/register", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login/send-code", views.LoginSendCodeView.as_view(), name="auth-login-send-code"),
    path("auth/login", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/sso/login", views.SSOReservedView.as_view(), name="auth-sso-login"),
    path("auth/sso/callback", views.SSOReservedView.as_view(), name="auth-sso-callback"),
    path("me", views.MeView.as_view(), name="me"),
    path("me/privacy-consent", views.PrivacyConsentView.as_view(), name="privacy-consent"),
]

if development_login_enabled():
    urlpatterns.append(path("auth/dev-login", views.DevLoginView.as_view(), name="auth-dev-login"))
