from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command

from apps.core import clock
from apps.notifications.models import Notification
from apps.recruitments.state import sync_recruitment
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class SyncCommandTest(TxTestCase):
    def test_candidates_boundaries_and_idempotence(self):
        now = clock.now()
        publisher = make_user()
        due = make_recruitment(publisher, deadline=now)
        overdue = make_recruitment(publisher, status="closed", closed_at=now - timedelta(days=7), close_reason="manual")
        app = make_application(overdue, make_user())
        untouched = [
            make_recruitment(publisher, deadline=now + timedelta(seconds=1)),
            make_recruitment(publisher, status="closed", closed_at=now - timedelta(days=7) + timedelta(seconds=1), close_reason="manual"),
            make_recruitment(publisher, status="closed", closed_at=now - timedelta(days=8), close_reason="manual"),
            make_recruitment(publisher, deadline=now, deleted_at=now),
            make_recruitment(publisher, status="full", full_at=now, deadline=now),
        ]
        make_application(untouched[1], make_user())
        before = {r.pk: (r.status, r.closed_at) for r in untouched}
        output = StringIO()
        with clock.freeze(now), mock.patch("apps.notifications.mail.dispatch"):
            call_command("run_sync_recruitments", stdout=output)
            self.assertIn("处理 2 个，失败 0 个，关闭 1 个，自动拒绝 1 份申请", output.getvalue())
            count = Notification.objects.count()
            second = StringIO()
            call_command("run_sync_recruitments", stdout=second)
        self.assertIn("处理 0 个", second.getvalue())
        self.assertEqual(Notification.objects.count(), count)
        due.refresh_from_db()
        app.refresh_from_db()
        self.assertEqual((due.status, due.closed_at), ("closed", now))
        self.assertEqual((app.status, app.decided_at), ("rejected", now))
        for r in untouched:
            r.refresh_from_db()
            self.assertEqual((r.status, r.closed_at), before[r.pk])

    def test_failure_does_not_stop_next_recruitment(self):
        now = clock.now()
        publisher = make_user()
        first = make_recruitment(publisher, deadline=now)
        second = make_recruitment(publisher, deadline=now)

        def sync(recruitment_id, *, now):
            if recruitment_id == first.pk:
                raise RuntimeError("simulated failure")
            return sync_recruitment(recruitment_id, now=now)

        output = StringIO()
        with clock.freeze(now), mock.patch("apps.notifications.mail.dispatch"), mock.patch(
            "apps.recruitments.management.commands.run_sync_recruitments.sync_recruitment", side_effect=sync,
        ), self.assertLogs("apps.recruitments.management.commands.run_sync_recruitments", level="ERROR"):
            call_command("run_sync_recruitments", stdout=output)
        self.assertIn("处理 1 个，失败 1 个，关闭 1 个", output.getvalue())
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ("open", "closed"))
