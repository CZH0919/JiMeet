from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import mock

from django.db import connection, connections, transaction

from apps.applications.models import Application
from apps.core import clock, tx
from apps.core.errors import Conflict, ErrorCode, NotFound
from apps.notifications.models import Notification
from apps.notifications import types
from apps.recruitments.models import Recruitment
from apps.recruitments.state import (
    mark_full, reject_processing_applications, run_in_recruitment_tx, sync_recruitment,
)
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


class StateTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.now = clock.now()
        self.publisher = make_user()
        self.r = make_recruitment(self.publisher, deadline=self.now)
        self.app = make_application(self.r, make_user(), publisher_mark="hold", has_unseen_update=True)
        patcher = mock.patch("apps.notifications.mail.dispatch")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_deadline_and_seven_day_boundaries_are_idempotent(self):
        with self.freeze_at(self.now):
            self.assertFalse(sync_recruitment(self.r.pk, now=self.now - timedelta(seconds=1)).closed)
            result = sync_recruitment(self.r.pk, now=self.now)
            self.assertTrue(result.closed)
            self.assertEqual(result.auto_rejected, 0)
            self.r.refresh_from_db()
            self.assertEqual((self.r.status, self.r.closed_at, self.r.close_reason), ("closed", self.now, "deadline"))
            end = self.now + timedelta(days=7)
            self.assertEqual(sync_recruitment(self.r.pk, now=end - timedelta(seconds=1)).auto_rejected, 0)
            self.assertEqual(sync_recruitment(self.r.pk, now=end).auto_rejected, 1)
            for _ in range(3):
                result = sync_recruitment(self.r.pk, now=end)
                self.assertEqual((result.closed, result.auto_rejected, result.became_full), (False, 0, False))
        self.app.refresh_from_db()
        self.assertEqual((self.app.status, self.app.decided_at, self.app.publisher_mark, self.app.has_unseen_update),
                         ("rejected", end, "none", False))
        closed_notice = Notification.objects.get(type=types.RECRUITMENT_CLOSED)
        self.assertEqual((closed_notice.recipient_id, closed_notice.recruitment_id,
                          closed_notice.application_id), (self.publisher.pk, self.r.pk, None))
        self.assertEqual(Notification.objects.filter(type=types.APPLICATION_REJECTED).count(), 1)
        self.assertIsNone(tx.held_recruitment_id())

    def test_timeout_notifies_each_processing_applicant_and_preserves_decided(self):
        other = make_application(self.r, make_user())
        decided = [make_application(self.r, make_user(), status=status)
                   for status in ("accepted", "withdrawn", "rejected", "invalid")]
        Recruitment.objects.filter(pk=self.r.pk).update(accepted_count=1)
        snapshots = {app.pk: Application.objects.values().get(pk=app.pk) for app in decided}
        end = self.now + timedelta(days=7)
        with self.freeze_at(end):
            self.assertEqual(sync_recruitment(self.r.pk).auto_rejected, 2)
            self.assertEqual(sync_recruitment(self.r.pk).auto_rejected, 0)
        notices = Notification.objects.filter(type=types.APPLICATION_REJECTED)
        self.assertEqual(notices.count(), 2)
        for app in (self.app, other):
            app.refresh_from_db()
            self.assertEqual((app.status, app.decided_at), ("rejected", end))
            notice = notices.get(application_id=app.pk)
            self.assertEqual((notice.recipient_id, notice.recruitment_id), (app.applicant_id, self.r.pk))
        for app in decided:
            self.assertEqual(Application.objects.values().get(pk=app.pk), snapshots[app.pk])
            self.assertFalse(Notification.objects.filter(application_id=app.pk).exists())
        self.r.refresh_from_db()
        self.assertEqual(self.r.accepted_count, 1)

    def test_delayed_task_preserves_business_times(self):
        with self.freeze_at(self.now + timedelta(days=30)):
            result = sync_recruitment(self.r.pk)
        self.assertEqual((result.closed, result.auto_rejected), (True, 1))
        self.r.refresh_from_db()
        self.app.refresh_from_db()
        self.assertEqual(self.r.closed_at, self.now)
        self.assertEqual(self.app.decided_at, self.now + timedelta(days=7))

    def test_deleted_and_full_are_unchanged(self):
        self.r.deleted_at = self.now
        self.r.save(update_fields=["deleted_at"])
        self.assertFalse(sync_recruitment(self.r.pk).closed)
        self.r.deleted_at = None
        self.r.status = "full"
        self.r.full_at = self.now
        self.r.save(update_fields=["deleted_at", "status", "full_at"])
        self.assertEqual(sync_recruitment(self.r.pk).auto_rejected, 0)

    def test_mark_full_preserves_or_adds_close_time(self):
        cases = (
            ("open", self.now + timedelta(days=1), None, None),
            ("open", self.now - timedelta(days=1), None, "deadline"),
            ("closed", self.now + timedelta(days=1), self.now - timedelta(hours=1), "manual"),
        )
        for status, deadline, closed_at, reason in cases:
            with self.subTest(status=status, reason=reason):
                r = make_recruitment(self.publisher, status=status, deadline=deadline,
                                     closed_at=closed_at, close_reason="manual" if closed_at else None)
                app = make_application(r, make_user())
                with tx.recruitment_lock_scope(), transaction.atomic():
                    locked = tx.lock_recruitment(r.pk)
                    locked.accepted_count = locked.max_headcount
                    mark_full(locked, self.now)
                    mark_full(locked, self.now + timedelta(seconds=1))
                r.refresh_from_db()
                app.refresh_from_db()
                self.assertEqual((r.status, r.full_at, r.accepted_count), ("full", self.now, r.max_headcount))
                self.assertEqual(r.closed_at, closed_at or (deadline if reason == "deadline" else None))
                self.assertEqual(r.close_reason, reason)
                self.assertEqual((app.status, app.decided_at), ("rejected", self.now))
                self.assertEqual(Notification.objects.filter(application=app).count(), 1)

    def test_lock_preconditions_and_transaction_identity(self):
        with transaction.atomic():
            with self.assertRaises(RuntimeError):
                mark_full(self.r, self.now)
            locked = tx.lock_recruitment(self.r.pk)
            self.assertEqual(tx.held_recruitment_id(), self.r.pk)
            with self.assertRaises(ValueError):
                mark_full(locked, self.now)
        with transaction.atomic():
            self.assertIsNone(tx.held_recruitment_id())
            with self.assertRaises(RuntimeError):
                tx.lock_application(self.app.pk, locked)
            with self.assertRaises(RuntimeError):
                reject_processing_applications(locked, self.now, "full")
        with transaction.atomic():
            try:
                with transaction.atomic():
                    rolled_back = tx.lock_recruitment(self.r.pk)
                    raise ValueError()
            except ValueError:
                pass
            with self.assertRaises(RuntimeError):
                tx.lock_application(self.app.pk, rolled_back)

    def test_callback_failure_does_not_rollback_sync(self):
        def reject(r, now):
            self.assertEqual(now, self.now)
            r.title = "不应保存"
            r.save(update_fields=["title"])
            raise Conflict(ErrorCode.RECRUITMENT_NOT_OPEN)

        with self.freeze_at(self.now), self.assertRaises(Conflict):
            run_in_recruitment_tx(self.r.pk, reject)
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, "closed")
        self.assertNotEqual(self.r.title, "不应保存")
        self.assertEqual(Notification.objects.count(), 1)
        self.assertIsNone(tx.held_recruitment_id())
        self.assertEqual(run_in_recruitment_tx(self.r.pk, lambda r, now: r.pk), self.r.pk)
        with transaction.atomic(), self.assertRaises(RuntimeError):
            run_in_recruitment_tx(self.r.pk, lambda r, now: None)
        with self.assertRaises(NotFound):
            run_in_recruitment_tx(10**9, lambda r, now: None)

    def test_notification_failure_rolls_back_sync(self):
        with mock.patch("apps.recruitments.state.notify", side_effect=RuntimeError("notify failed")):
            with self.assertRaises(RuntimeError):
                sync_recruitment(self.r.pk, now=self.now)
        self.r.refresh_from_db()
        self.assertEqual(self.r.status, "open")
        self.assertIsNone(tx.held_recruitment_id())

    def test_concurrent_accept_only_counts_once(self):
        if connection.vendor != "postgresql":
            self.skipTest("需要 PostgreSQL 行锁")
        Recruitment.objects.filter(pk=self.r.pk).update(deadline=self.now + timedelta(days=1))
        barrier = Barrier(2, timeout=10)

        def accept():
            connections.close_all()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                barrier.wait()
                with tx.recruitment_lock_scope(), transaction.atomic():
                    r = tx.lock_recruitment(self.r.pk)
                    app = tx.lock_application(self.app.pk, r)
                    if app.status != "processing":
                        return False
                    app.status = "accepted"
                    app.decided_at = self.now
                    app.save(update_fields=["status", "decided_at", "updated_at"])
                    r.accepted_count += 1
                    r.save(update_fields=["accepted_count", "updated_at"])
                    return True
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(accept) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(results), [False, True])
        self.r.refresh_from_db()
        self.assertEqual(self.r.accepted_count, 1)
        self.assertEqual(Application.objects.get(pk=self.app.pk).status, "accepted")

    def test_concurrent_different_applications_compete_for_last_place(self):
        if connection.vendor != "postgresql":
            self.skipTest("需要 PostgreSQL 行锁")
        Recruitment.objects.filter(pk=self.r.pk).update(
            deadline=self.now + timedelta(days=1), max_headcount=1,
        )
        other = make_application(self.r, make_user())
        barrier = Barrier(2, timeout=10)

        def compete(application_id):
            connections.close_all()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                barrier.wait()
                with tx.recruitment_lock_scope(), transaction.atomic():
                    r = tx.lock_recruitment(self.r.pk)
                    app = tx.lock_application(application_id, r)
                    if app.status != "processing" or r.status != "open" or r.accepted_count >= r.max_headcount:
                        return False
                    app.status = "accepted"
                    app.decided_at = self.now
                    app.save(update_fields=["status", "decided_at", "updated_at"])
                    r.accepted_count += 1
                    mark_full(r, self.now)
                    return True
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(compete, app.pk) for app in (self.app, other)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(results), [False, True])
        self.r.refresh_from_db()
        self.assertEqual((self.r.status, self.r.accepted_count, self.r.full_at), ("full", 1, self.now))
        applications = Application.objects.filter(recruitment=self.r)
        self.assertEqual(applications.filter(status="accepted").count(), 1)
        loser = applications.get(status="rejected")
        self.assertEqual(loser.decided_at, self.now)
        notice = Notification.objects.get(type=types.APPLICATION_REJECTED)
        self.assertEqual((notice.application_id, notice.recipient_id, notice.recruitment_id),
                         (loser.pk, loser.applicant_id, self.r.pk))
