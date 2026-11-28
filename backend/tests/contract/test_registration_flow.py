"""通过回环 HTTP、独立数据库及隔离收件箱验收注册链路。"""
import json
import re
from datetime import timedelta
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request

from django.conf import settings
from django.core import mail
from django.db.models import F
from django.test import LiveServerTestCase

from apps.accounts.models import RegistrationMailRequest, User


class RegistrationHTTPTest(LiveServerTestCase):
    def test_mail_verification_registration_and_password_login(self):
        cookies = CookieJar()
        browser = build_opener(HTTPCookieProcessor(cookies))
        api = self.live_server_url + "/api/v1"
        address = "registration-flow@tongji.edu.cn"
        password = "Integration-Test!7845"

        def request(path, *, body=None, csrf=None, status=200):
            headers = {}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers.update({"Content-Type": "application/json", "X-CSRFToken": csrf, "Origin": self.live_server_url})
            with browser.open(Request(api + path, data=data, headers=headers), timeout=8) as response:
                self.assertEqual(response.status, status)
                payload = json.load(response)
                self.assertEqual(payload["code"], "OK")
                return payload["data"]

        csrf = request("/auth/csrf")["csrf_token"]
        request("/auth/register/send-code", body={"email": address}, csrf=csrf)
        anonymous_session = next(cookie.value for cookie in cookies if cookie.name == settings.SESSION_COOKIE_NAME)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [address])
        code = re.search(r"验证码为 ([0-9]{6})", mail.outbox[0].body).group(1)
        verified = request("/auth/register/verify-code", body={"email": address, "code": code}, csrf=csrf)
        self.assertEqual(verified["account_exists"], False)
        self.assertFalse(User.objects.filter(email=address).exists())
        profile = request("/auth/register", body={
            "name": "测试同学", "email": address, "password": password,
            "password_confirm": password, "role": "student",
        }, csrf=csrf, status=201)
        self.assertFalse(profile["is_admin"])
        self.assertFalse(profile["privacy_consented"])
        authenticated_session = next(cookie.value for cookie in cookies if cookie.name == settings.SESSION_COOKIE_NAME)
        self.assertNotEqual(authenticated_session, anonymous_session)
        self.assertEqual(request("/me")["uid"], profile["uid"])
        self.assertTrue(User.objects.get(email=address).check_password(password))
        csrf = request("/auth/csrf")["csrf_token"]
        request("/auth/logout", body={}, csrf=csrf)
        csrf = request("/auth/csrf")["csrf_token"]
        signed_in = request("/auth/login", body={"email": address, "password": password}, csrf=csrf)
        self.assertEqual(signed_in["uid"], profile["uid"])
        self.assertEqual(request("/me")["uid"], profile["uid"])

        # 验证码登录（双方式）：跳过重发冷却后取登录码
        csrf = request("/auth/csrf")["csrf_token"]
        request("/auth/logout", body={}, csrf=csrf)
        RegistrationMailRequest.objects.update(
            requested_at=F("requested_at") - timedelta(seconds=61),
        )
        csrf = request("/auth/csrf")["csrf_token"]
        request("/auth/login/send-code", body={"email": address}, csrf=csrf)
        login_code = re.search(r"验证码为 ([0-9]{6})", mail.outbox[-1].body).group(1)
        signed_in = request("/auth/login", body={"email": address, "code": login_code}, csrf=csrf)
        self.assertEqual(signed_in["uid"], profile["uid"])
        self.assertEqual(request("/me")["uid"], profile["uid"])

        # 重复注册提示仅在验码后出现
        RegistrationMailRequest.objects.update(
            requested_at=F("requested_at") - timedelta(seconds=61),
        )
        csrf = request("/auth/csrf")["csrf_token"]
        request("/auth/register/send-code", body={"email": address}, csrf=csrf)
        code = re.search(r"验证码为 ([0-9]{6})", mail.outbox[-1].body).group(1)
        verified = request("/auth/register/verify-code", body={"email": address, "code": code}, csrf=csrf)
        self.assertTrue(verified["account_exists"])
        self.assertEqual(verified["expires_in"], 0)
