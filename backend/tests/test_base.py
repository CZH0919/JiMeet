from datetime import datetime, timezone as dt_timezone

from apps.core.clock import now
from tests.base import TxTestCase
from tests.factories import make_user


class TxTestCaseTest(TxTestCase):
    def test_login_sets_session_user(self):
        user = make_user()
        self.login(user)
        response = self.client.get("/api/v1/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_freeze_at(self):
        moment = datetime(2026, 3, 1, tzinfo=dt_timezone.utc)
        with self.freeze_at(moment):
            self.assertEqual(now(), moment)
        self.assertNotEqual(now(), moment)

    def test_reset_sequences_disabled(self):
        self.assertFalse(self.reset_sequences)


class MakeUserTest(TxTestCase):
    def test_defaults(self):
        user = make_user()
        self.assertEqual(user.role, "student")
        self.assertFalse(user.is_admin)
        self.assertIsNotNone(user.privacy_consented_at)
        self.assertTrue(user.check_password("") is False)
        self.assertFalse(user.has_usable_password())

    def test_teacher_and_admin(self):
        user = make_user(role="teacher", is_admin=True)
        self.assertEqual(user.role, "teacher")
        self.assertTrue(user.is_admin)
        self.assertTrue(user.real_id.startswith("t"))

    def test_privacy_false(self):
        self.assertIsNone(make_user(privacy=False).privacy_consented_at)

    def test_unique_real_id(self):
        first = make_user()
        second = make_user()
        self.assertNotEqual(first.real_id, second.real_id)
