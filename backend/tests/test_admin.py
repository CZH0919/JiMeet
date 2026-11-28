from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import User
from apps.announcements.models import Announcement
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

    def test_create_user_hashes_password_and_ignores_business_admin_flag(self):
        response = self.client.post(reverse("admin:accounts_user_add"), {
            "real_id": "s-admin", "name": "学生管理员", "email": "student-admin@tongji.edu.cn",
            "nickname": "学生", "role": "student", "password1": "Strong-test-password-37",
            "password2": "Strong-test-password-37", "is_active": "on", "is_admin": "on",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(real_id="s-admin")
        self.assertFalse(user.is_admin)
        self.assertTrue(user.check_password("Strong-test-password-37"))
        self.assertFalse(user.is_staff)

    def test_announcement_readonly_and_business_role_forms(self):
        request = RequestFactory().get("/admin/")
        request.user = self.user
        panel = admin.site.get_model_admin(Announcement)
        self.assertTrue(panel.has_view_permission(request))
        self.assertFalse(panel.has_add_permission(request))
        self.assertFalse(panel.has_change_permission(request))
        self.assertFalse(panel.has_delete_permission(request))
        self.assertNotIn("delete_selected", panel.get_actions(request))
        users = admin.site.get_model_admin(User)
        for obj in (None, self.user):
            self.assertNotIn("is_admin", users.get_form(request, obj=obj).base_fields)
