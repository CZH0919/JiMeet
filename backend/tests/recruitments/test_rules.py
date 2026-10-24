from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.core.errors import ValidationFailed
from apps.recruitments import rules
from apps.recruitments.policies import (
    can_close, can_delete, can_edit, can_view_applications, publish_state_for_viewer,
)


class RulesTest(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2024, 2, 29, tzinfo=timezone.utc)
        self.r = SimpleNamespace(
            publisher_id=1, deadline=self.now + timedelta(days=1),
            status="open", closed_at=None, full_at=None, deleted_at=None,
        )

    def test_calendar_and_deadline_boundaries(self):
        end = datetime(2025, 2, 28, tzinfo=timezone.utc)
        self.assertEqual(rules.add_one_year(self.now), end)
        rules.validate_deadline(end, self.now)
        for deadline in (self.now, end + timedelta(seconds=1)):
            with self.subTest(deadline=deadline), self.assertRaises(ValidationFailed):
                rules.validate_deadline(deadline, self.now)

    @override_settings(MAX_HEADCOUNT_LIMIT=50)
    def test_headcount(self):
        for minimum, maximum in ((None, 1), (1, 50), (50, 50)):
            rules.validate_headcount(minimum, maximum)
        for minimum, maximum in ((None, 0), (None, 51), (0, 3), (4, 3), (True, 3), (None, 1.5)):
            with self.subTest(minimum=minimum, maximum=maximum), self.assertRaises(ValidationFailed):
                rules.validate_headcount(minimum, maximum)

    def test_status_and_time_windows(self):
        for check in (rules.is_apply_open, rules.is_editable, rules.is_publisher_deletable, rules.is_processable):
            self.assertTrue(check(self.r, self.now))
            self.assertFalse(check(self.r, self.r.deadline))
        self.r.status = "closed"
        self.r.closed_at = self.now
        end = self.now + timedelta(days=7)
        self.assertEqual(rules.seven_day_deadline(self.r), end)
        self.assertTrue(rules.is_processable(self.r, end - timedelta(seconds=1)))
        self.assertFalse(rules.is_processable(self.r, end))
        self.assertFalse(rules.is_apply_open(self.r, self.now))
        self.r.status = "full"
        self.assertFalse(rules.is_processable(self.r, self.now))
        self.r.status = "open"
        self.r.deleted_at = self.now
        for check in (rules.is_apply_open, rules.is_editable, rules.is_publisher_deletable, rules.is_processable):
            self.assertFalse(check(self.r, self.now))

    def test_retention_uses_earliest_event(self):
        self.assertIsNone(rules.seven_day_deadline(self.r))
        self.assertIsNone(rules.retention_starts_at(self.r))
        self.assertIsNone(rules.retention_expires_at(self.r))
        self.assertFalse(rules.is_retention_expired(self.r, self.now))
        self.r.full_at = self.now
        self.r.closed_at = self.now + timedelta(days=2)
        self.r.deleted_at = self.now + timedelta(days=3)
        end = self.now + timedelta(days=180)
        self.assertEqual(rules.retention_starts_at(self.r), self.now)
        self.assertEqual(rules.retention_expires_at(self.r), end)
        self.assertFalse(rules.is_retention_expired(self.r, end - timedelta(seconds=1)))
        self.assertTrue(rules.is_retention_expired(self.r, end))

    def test_closed_recruitment_is_not_editable_or_deletable(self):
        self.r.status = "closed"
        self.r.closed_at = self.now
        self.assertFalse(rules.is_editable(self.r, self.now))
        self.assertFalse(rules.is_publisher_deletable(self.r, self.now))
        publisher = SimpleNamespace(pk=1, is_authenticated=True, is_admin=False)
        self.assertFalse(can_edit(publisher, self.r, self.now))
        self.assertFalse(can_close(publisher, self.r, self.now))
        self.assertFalse(can_delete(publisher, self.r, self.now))

    def test_close_and_edit_boundaries_and_other_users(self):
        publisher = SimpleNamespace(pk=1, is_authenticated=True, is_admin=False)
        stranger = SimpleNamespace(pk=5, is_authenticated=True, is_admin=False)
        anonymous = SimpleNamespace(pk=None, is_authenticated=False, is_admin=False)
        self.assertFalse(can_close(publisher, self.r, self.r.deadline))
        self.assertFalse(can_edit(publisher, self.r, self.r.deadline))
        for user in (stranger, anonymous):
            for check in (can_edit, can_close, can_delete):
                with self.subTest(user=user.pk, check=check.__name__):
                    self.assertFalse(check(user, self.r, self.now))
            self.assertFalse(can_view_applications(user, self.r))
        self.assertEqual(
            publish_state_for_viewer(anonymous, self.r, self.now).can_apply, True,
        )

    def test_retention_starts_from_earliest_of_each_field(self):
        base = self.now
        for field in ("closed_at", "full_at", "deleted_at"):
            with self.subTest(earliest=field):
                self.r.closed_at = self.r.full_at = self.r.deleted_at = None
                for index, name in enumerate(("closed_at", "full_at", "deleted_at")):
                    later = base + timedelta(days=index + 1)
                    setattr(self.r, name, base if name == field else later)
                self.assertEqual(rules.retention_starts_at(self.r), base)
                self.assertEqual(rules.retention_expires_at(self.r), base + timedelta(days=180))

    def test_recruitment_permissions(self):
        publisher = SimpleNamespace(pk=1, is_authenticated=True, is_admin=False)
        admin = SimpleNamespace(pk=2, is_authenticated=True, is_admin=True)
        for check in (can_edit, can_close, can_delete):
            self.assertTrue(check(publisher, self.r, self.now))
        self.assertTrue(can_view_applications(publisher, self.r))
        self.assertFalse(can_view_applications(admin, self.r))
        self.assertFalse(can_edit(admin, self.r, self.now))
        self.assertEqual(publish_state_for_viewer(publisher, self.r, self.now).apply_blocked_reason, "own")
        self.assertTrue(publish_state_for_viewer(admin, self.r, self.now).can_apply)
        self.r.status = "full"
        self.assertFalse(can_delete(publisher, self.r, self.now))
        self.assertTrue(can_delete(admin, self.r, self.now))
        self.assertEqual(publish_state_for_viewer(admin, self.r, self.now).apply_blocked_reason, "not_open")
        self.r.deleted_at = self.now
        self.assertFalse(can_delete(admin, self.r, self.now))
