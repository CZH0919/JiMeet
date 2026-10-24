from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import User
from apps.chat.models import ChatConversation, ChatMessage
from apps.recruitments.models import Tag
from tests.base import TxTestCase


class AdminTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_superuser(
            real_id="t-admin", name="后台用户", email="admin@tongji.edu.cn",
            nickname="管理员", password="admin-test-password",
        )
        self.login(self.user)

    def test_registration(self):
        self.assertTrue(admin.site.is_registered(User))
        self.assertTrue(admin.site.is_registered(Tag))
        self.assertFalse(admin.site.is_registered(ChatConversation))
        self.assertFalse(admin.site.is_registered(ChatMessage))

    def test_user_forms_render(self):
        for url in (reverse(
            "admin:accounts_user_add",
        ), reverse("admin:accounts_user_change", args=[self.user.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_create_user_hashes_password_and_accepts_admin_flag(self):
        response = self.client.post(reverse("admin:accounts_user_add"), {
            "real_id": "s-admin", "name": "学生管理员", "email": "student-admin@tongji.edu.cn",
            "nickname": "学生", "role": "student", "password1": "Strong-test-password-37",
            "password2": "Strong-test-password-37", "is_active": "on", "is_admin": "on",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(real_id="s-admin")
        self.assertTrue(user.is_admin)
        self.assertTrue(user.check_password("Strong-test-password-37"))
        self.assertFalse(user.is_staff)
