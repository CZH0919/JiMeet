from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.core.errors import Forbidden, NotAuthenticated
from apps.core.permissions import IsAdminFlag, IsAuthenticatedBiz


def _request(user):
    return SimpleNamespace(user=user)


def _user(is_authenticated=True, is_admin=False):
    return SimpleNamespace(is_authenticated=is_authenticated, is_admin=is_admin)


class PermissionsTest(SimpleTestCase):
    def test_anonymous_rejected(self):
        for permission in (IsAuthenticatedBiz(), IsAdminFlag()):
            with self.subTest(permission=type(permission).__name__):
                with self.assertRaises(NotAuthenticated):
                    permission.has_permission(_request(_user(is_authenticated=False)), None)

    def test_authenticated_allowed(self):
        self.assertTrue(IsAuthenticatedBiz().has_permission(_request(_user()), None))

    def test_admin_flag_only(self):
        self.assertTrue(
            IsAdminFlag().has_permission(_request(_user(is_admin=True)), None)
        )
        with self.assertRaises(Forbidden):
            IsAdminFlag().has_permission(_request(_user(is_admin=False)), None)
