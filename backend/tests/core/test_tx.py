import unittest

from django.db import transaction
from django.test import TransactionTestCase

from apps.core import tx
from apps.core.errors import NotFound


def _models_ready() -> bool:
    try:
        from apps.applications.models import Application  # noqa: F401
        from apps.recruitments.models import Recruitment  # noqa: F401
    except ImportError:
        return False
    return True


MODELS_READY = _models_ready()


class AtomicAssertTest(TransactionTestCase):
    def test_assert_not_in_atomic_passes_outside(self):
        tx.assert_not_in_atomic()

    def test_assert_not_in_atomic_raises_inside(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                tx.assert_not_in_atomic()

    def test_assert_in_atomic_raises_outside(self):
        with self.assertRaises(RuntimeError):
            tx.assert_in_atomic()

    def test_assert_in_atomic_passes_inside(self):
        with transaction.atomic():
            tx.assert_in_atomic()


@unittest.skipUnless(MODELS_READY, "Recruitment / Application 模型尚未实现")
class LockTest(TransactionTestCase):
    def setUp(self):
        from tests.factories import make_application, make_recruitment, make_user

        self.publisher = make_user(role="teacher")
        self.applicant = make_user()
        self.recruitment = make_recruitment(self.publisher)
        self.application = make_application(self.recruitment, self.applicant)

    def test_lock_recruitment_requires_atomic(self):
        with self.assertRaises(RuntimeError):
            tx.lock_recruitment(self.recruitment.id)

    def test_lock_recruitment_missing_raises_not_found(self):
        with self.assertRaises(NotFound):
            with transaction.atomic():
                tx.lock_recruitment(10**9)

    def test_lock_application_requires_recruitment_lock(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                tx.lock_application(self.application.id, self.recruitment)

    def test_lock_application_rejects_other_recruitment(self):
        from tests.factories import make_recruitment

        other = make_recruitment(self.publisher)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                locked = tx.lock_recruitment(other.id)
                tx.lock_application(self.application.id, locked)

    def test_lock_application_ok(self):
        with transaction.atomic():
            locked = tx.lock_recruitment(self.recruitment.id)
            application = tx.lock_application(self.application.id, locked)
        self.assertEqual(application.id, self.application.id)

    def test_peek_returns_recruitment_id(self):
        self.assertEqual(
            tx.peek_application_recruitment_id(self.application.id), self.recruitment.id
        )

    def test_peek_missing_raises_not_found(self):
        with self.assertRaises(NotFound):
            tx.peek_application_recruitment_id(10**9)
