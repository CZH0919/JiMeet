"""申请历史、时间边界及删除竞争的事务回归。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import mock
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connections, transaction

from apps.applications.models import Application, ApplicationStatusHistory
from apps.applications.services import perform_application_action
from apps.core import clock, tx
from apps.core.errors import BizError
from apps.notifications.models import Notification
from apps.recruitments import services, state
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class ApplicationHistoryTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user()
        self.admin = make_user(is_admin=True)
        self.applicant = make_user()
        self.r = make_recruitment(self.owner)
        self.app = make_application(self.r, self.applicant)

    def _parallel(self, jobs):
        gate = Barrier(len(jobs))

        def run(job):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                return job()
            except BizError as error:
                return error.http_status
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return [future.result(timeout=30) for future in futures]

    def test_manual_transitions_record_actor_and_deletion_keeps_acceptance(self):
        perform_application_action(self.owner, self.app.pk, "hold")
        perform_application_action(self.owner, self.app.pk, "unhold")
        self.assertFalse(ApplicationStatusHistory.objects.exists())
        perform_application_action(self.owner, self.app.pk, "accept")
        self.app.refresh_from_db()
        accepted_at = self.app.decided_at
        services.delete_recruitment(self.owner, self.r.pk)
        self.app.refresh_from_db()
        self.assertEqual(self.app.decided_at, accepted_at)
        self.assertEqual(list(self.app.status_history.values_list("from_status", "to_status", "reason", "actor_id")), [
            ("processing", "accepted", "accept", self.owner.pk),
            ("accepted", "invalid", "delete_invalid", self.owner.pk),
        ])

    def test_reject_and_withdraw_record_separate_reasons(self):
        perform_application_action(self.applicant, self.app.pk, "withdraw")
        another = make_application(self.r, make_user())
        perform_application_action(self.owner, another.pk, "reject")
        self.assertEqual(ApplicationStatusHistory.objects.get(application=self.app).reason, "withdraw")
        self.assertEqual(ApplicationStatusHistory.objects.get(application=another).reason, "reject_manual")

    def test_batch_sync_reconciles_full_before_deadline_without_duplicate_history(self):
        self.r.status = "full"; self.r.max_headcount = 1; self.r.accepted_count = 1
        self.r.full_at = clock.now()
        self.r.save(update_fields=["status", "max_headcount", "accepted_count", "full_at"])
        make_application(self.r, make_user(), status="accepted")
        call_command("run_sync_recruitments", stdout=StringIO())
        call_command("run_sync_recruitments", stdout=StringIO())
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "rejected")
        self.assertEqual(self.app.status_history.get().reason, "auto_full")

    def test_delayed_timeout_records_business_time_once_without_fabricating_history(self):
        self.r.status = "closed"
        self.r.closed_at = clock.now() - timedelta(days=365)
        self.r.close_reason = "manual"
        self.r.save(update_fields=["status", "closed_at", "close_reason"])
        end = self.r.closed_at + timedelta(days=7)
        state.sync_recruitment(self.r.pk)
        state.sync_recruitment(self.r.pk)
        event = ApplicationStatusHistory.objects.get(application=self.app)
        self.assertEqual((event.from_status, event.to_status, event.reason, event.actor_id), ("processing", "rejected", "auto_window", None))
        self.assertEqual(event.occurred_at, end)
        self.assertGreater(event.created_at, event.occurred_at)

    def test_processing_window_boundaries_and_projection_do_not_write_history(self):
        from apps.applications.selectors import get_application

        end = clock.now()
        self.r.status = "closed"; self.r.closed_at = end - timedelta(days=7); self.r.close_reason = "manual"
        self.r.save(update_fields=["status", "closed_at", "close_reason"])
        projected = get_application(self.applicant, self.app.pk, end)
        self.assertEqual(projected.status, "rejected")
        self.assertFalse(ApplicationStatusHistory.objects.exists())
        with self.freeze_at(end - timedelta(microseconds=1)):
            perform_application_action(self.owner, self.app.pk, "hold")
        with self.freeze_at(end):
            with self.assertRaises(BizError):
                perform_application_action(self.applicant, self.app.pk, "withdraw")
        self.assertEqual(ApplicationStatusHistory.objects.get(application=self.app).reason, "auto_window")

    def test_time_is_rechecked_after_waiting_for_the_second_lock(self):
        before = clock.now()
        deadline = before + timedelta(seconds=1)
        self.r.deadline = deadline; self.r.save(update_fields=["deadline"])
        current = [before]; calls = [0]; original = tx.lock_recruitment

        def lock(recruitment_id):
            result = original(recruitment_id)
            calls[0] += 1
            if calls[0] == 2:
                current[0] = deadline
            return result

        with mock.patch.object(clock, "now", side_effect=lambda: current[0]):
            with mock.patch.object(tx, "lock_recruitment", side_effect=lock):
                result = state.run_in_recruitment_tx(self.r.pk, lambda r, now: (r.status, now))
        self.assertEqual(result, ("closed", deadline))
        self.assertEqual(Notification.objects.filter(type="recruitment_closed").count(), 1)

    def test_last_of_200_slots_and_concurrent_acceptance_are_consistent(self):
        self.r.max_headcount = 200; self.r.accepted_count = 199
        self.r.save(update_fields=["max_headcount", "accepted_count"])
        for _ in range(199):
            make_application(self.r, make_user(), status="accepted")
        rival = make_application(self.r, make_user())
        self._parallel([
            lambda: perform_application_action(self.owner, self.app.pk, "accept"),
            lambda: perform_application_action(self.owner, rival.pk, "accept"),
        ])
        self.r.refresh_from_db()
        self.assertEqual((self.r.status, self.r.accepted_count), ("full", 200))
        self.assertEqual(Application.objects.filter(recruitment=self.r, status="accepted").count(), 200)
        self.assertEqual(sorted(ApplicationStatusHistory.objects.values_list("reason", flat=True)), ["accept", "auto_full"])

    def test_accept_and_delete_cannot_leave_an_accepted_deleted_application(self):
        self._parallel([
            lambda: perform_application_action(self.owner, self.app.pk, "accept"),
            lambda: services.governance_delete_recruitment(self.admin, self.r.pk, reason="治理原因"),
        ])
        self.r.refresh_from_db(); self.app.refresh_from_db()
        self.assertIsNotNone(self.r.deleted_at)
        self.assertEqual((self.r.accepted_count, self.app.status), (0, "invalid"))
        events = list(self.app.status_history.order_by("id").values_list("to_status", flat=True))
        self.assertIn(events, [["invalid"], ["accepted", "invalid"]])
        self.assertEqual(Notification.objects.filter(type="recruitment_deleted").count(), 1)

    def test_accept_withdraw_race_keeps_one_terminal_event(self):
        self._parallel([
            lambda: perform_application_action(self.owner, self.app.pk, "accept"),
            lambda: perform_application_action(self.applicant, self.app.pk, "withdraw"),
        ])
        self.r.refresh_from_db(); self.app.refresh_from_db()
        self.assertEqual(self.r.accepted_count, int(self.app.status == "accepted"))
        self.assertEqual(self.app.status_history.count(), 1)
        self.assertEqual(self.app.status_history.get().to_status, self.app.status)

    def test_history_failure_rolls_back_application_and_count(self):
        with mock.patch("apps.applications.services.record_status_changes", side_effect=RuntimeError("history unavailable")):
            with self.assertRaises(RuntimeError):
                perform_application_action(self.owner, self.app.pk, "accept")
        self.app.refresh_from_db(); self.r.refresh_from_db()
        self.assertEqual((self.app.status, self.r.accepted_count), ("processing", 0))
        self.assertFalse(Notification.objects.exists())

    def test_notification_failure_rolls_back_history_and_count(self):
        with mock.patch("apps.applications.services.notify", side_effect=RuntimeError("notification unavailable")):
            with self.assertRaises(RuntimeError):
                perform_application_action(self.owner, self.app.pk, "accept")
        self.app.refresh_from_db(); self.r.refresh_from_db()
        self.assertEqual((self.app.status, self.r.accepted_count), ("processing", 0))
        self.assertFalse(ApplicationStatusHistory.objects.exists())

    def test_database_rejects_invalid_or_duplicate_history(self):
        perform_application_action(self.owner, self.app.pk, "accept")
        event = self.app.status_history.get()
        for fields in (
            {"from_status": "accepted", "to_status": "processing", "reason": "accept", "actor": self.owner},
            {"from_status": "processing", "to_status": "accepted", "reason": "accept", "actor": None},
            {"from_status": "processing", "to_status": "accepted", "reason": "accept", "actor": self.owner},
        ):
            with self.subTest(fields=fields.keys()), self.assertRaises(IntegrityError), transaction.atomic():
                ApplicationStatusHistory.objects.create(application=self.app, recruitment=self.r, occurred_at=event.occurred_at, **fields)
