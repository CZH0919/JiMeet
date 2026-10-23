from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.clock import freeze, now


class ClockTest(SimpleTestCase):
    def test_now_is_aware(self):
        self.assertTrue(timezone.is_aware(now()))

    def test_freeze_overrides_and_restores(self):
        moment = datetime(2026, 1, 1, 12, 0, tzinfo=dt_timezone.utc)
        before = now()
        with freeze(moment):
            self.assertEqual(now(), moment)
        self.assertGreaterEqual(now(), before)

    def test_freeze_nests(self):
        outer = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        inner = outer + timedelta(days=1)
        with freeze(outer):
            with freeze(inner):
                self.assertEqual(now(), inner)
            self.assertEqual(now(), outer)
