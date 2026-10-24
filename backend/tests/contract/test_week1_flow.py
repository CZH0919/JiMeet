from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import override_settings

from apps.applications.models import Application
from apps.applications.policies import (
    can_process_application, can_submit_application, resolve_application_access,
)
from apps.core import clock, tx
from apps.core.errors import BizError, Conflict, ErrorCode, Forbidden, ValidationFailed
from apps.files.storage import staged_resume
from apps.notifications import types
from apps.notifications.models import Notification
from apps.notifications.service import notify
from apps.recruitments import rules
from apps.recruitments.models import Recruitment, RecruitmentTag
from apps.recruitments.state import mark_full, run_in_recruitment_tx
from tests.base import TxTestCase
from tests.factories import make_tag, make_user


def _publish(publisher, tags, *, max_headcount=1, deadline=None):
    """参考发布：校验规则与活动标签后，在事务内创建招聘及标签关系。"""
    now = clock.now()
    deadline = deadline if deadline is not None else now + timedelta(days=1)
    rules.validate_deadline(deadline, now)
    rules.validate_headcount(None, max_headcount)
    if not tags or any(not tag.is_active for tag in tags):
        raise ValidationFailed(details={"tags": "须选择启用的标签"})
    with transaction.atomic():
        recruitment = Recruitment.objects.create(
            publisher=publisher, title="契约招聘", description="流程参考", type="competition",
            max_headcount=max_headcount, deadline=deadline,
        )
        for tag in tags:
            RecruitmentTag.objects.create(recruitment=recruitment, tag=tag)
        return recruitment


def _apply(recruitment, applicant):
    """参考投递：先暂存文件，再补执行、加锁校验和创建完整申请。"""
    with staged_resume(SimpleUploadedFile("resume.pdf", b"%PDF-contract")) as stored:
        def create(locked, now):
            active = Application.objects.filter(recruitment=locked, applicant=applicant).exclude(status="withdrawn").exists()
            can_submit_application(applicant, locked, now, has_active_application=active)
            application = Application.objects.create(
                recruitment=locked, applicant=applicant, resume_file=stored.path,
                resume_name=stored.original_name, resume_size=stored.size, resume_type=stored.type,
            )
            notify(recipient=locked.publisher, type=types.APPLICATION_SUBMITTED,
                   recruitment=locked, application=application)
            return application
        return run_in_recruitment_tx(recruitment.pk, create)


def _accept(application, publisher):
    """参考接受：重新锁申请，复核窗口与状态，再更新人数及满员状态。"""
    def accept(recruitment, now):
        app = tx.lock_application(application.pk, recruitment)
        if publisher.pk != recruitment.publisher_id:
            raise Forbidden()
        # 补执行可能已将申请拒绝，先返回明确的七天窗口错误。
        end = rules.seven_day_deadline(recruitment)
        if recruitment.status == "closed" and end is not None and now >= end:
            raise Conflict(ErrorCode.PROCESSING_WINDOW_CLOSED)
        if not can_process_application(publisher, app, recruitment, now):
            raise Conflict(ErrorCode.APPLICATION_NOT_PROCESSING)
        app.status = "accepted"
        app.decided_at = now
        app.save(update_fields=["status", "decided_at", "updated_at"])
        recruitment.accepted_count += 1
        notify(recipient=app.applicant, type=types.APPLICATION_ACCEPTED,
               recruitment=recruitment, application=app)
        if recruitment.accepted_count == recruitment.max_headcount:
            mark_full(recruitment, now)
        else:
            recruitment.save(update_fields=["accepted_count", "updated_at"])
        return app
    return run_in_recruitment_tx(application.recruitment_id, accept)


class Week1FlowTest(TxTestCase):
    def setUp(self):
        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        settings = override_settings(PRIVATE_FILE_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        patcher = mock.patch("apps.notifications.mail.dispatch")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.publisher = make_user()
        self.a = make_user()
        self.b = make_user()
        self.tag = make_tag()

    def _assert_count_consistent(self, r):
        r.refresh_from_db()
        self.assertEqual(r.accepted_count, Application.objects.filter(recruitment=r, status="accepted").count())

    def _assert_notice(self, type, app, recipient):
        notice = Notification.objects.get(type=type, application=app)
        self.assertEqual((notice.recipient_id, notice.recruitment_id), (recipient.pk, app.recruitment_id))

    def test_one_place_full_flow(self):
        r = _publish(self.publisher, [self.tag])
        self.assertEqual(RecruitmentTag.objects.get(recruitment=r).tag_id, self.tag.pk)
        a, b = _apply(r, self.a), _apply(r, self.b)
        _accept(a, self.publisher)
        a.refresh_from_db()
        b.refresh_from_db()
        self._assert_count_consistent(r)
        self.assertEqual((a.status, b.status, r.status), ("accepted", "rejected", "full"))
        self._assert_notice(types.APPLICATION_ACCEPTED, a, self.a)
        self._assert_notice(types.APPLICATION_REJECTED, b, self.b)
        for app in (a, b):
            self._assert_notice(types.APPLICATION_SUBMITTED, app, self.publisher)
            self.assertTrue((self.root / app.resume_file.name).exists())
        self.assertEqual(Notification.objects.filter(recipient=self.a).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.b).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.publisher).count(), 2)
        self.assertFalse(Notification.objects.filter(type=types.RECRUITMENT_CLOSED).exists())
        access = resolve_application_access(make_user(is_admin=True), a, r, clock.now())
        self.assertEqual(access.relation, "none")
        self.assertFalse(any((access.can_view, access.can_see_note, access.can_see_applicant_name,
                              access.can_download_resume, access.can_see_publisher_mark)))

    def test_two_places_transition(self):
        r = _publish(self.publisher, [self.tag], max_headcount=2)
        a, b = _apply(r, self.a), _apply(r, self.b)
        _accept(a, self.publisher)
        self._assert_count_consistent(r)
        self.assertEqual((r.status, r.accepted_count), ("open", 1))
        _accept(b, self.publisher)
        self._assert_count_consistent(r)
        self.assertEqual((r.status, r.accepted_count), ("full", 2))

    def test_apply_rejections_cleanup_and_reapply(self):
        r = _publish(self.publisher, [self.tag])
        unconsented = make_user(privacy=False)
        for user, code in ((self.publisher, ErrorCode.SELF_APPLICATION_FORBIDDEN),
                           (unconsented, ErrorCode.PRIVACY_NOT_CONSENTED)):
            with self.assertRaises(BizError) as caught:
                _apply(r, user)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(list(self.root.rglob("*.pdf")), [])
        old = _apply(r, self.a)
        with self.assertRaises(BizError) as caught:
            _apply(r, self.a)
        self.assertEqual(caught.exception.code, ErrorCode.DUPLICATE_APPLICATION)
        self.assertEqual(len(list(self.root.rglob("*.pdf"))), 1)
        Application.objects.filter(pk=old.pk).update(status="withdrawn", decided_at=clock.now())
        new = _apply(r, self.a)
        self.assertNotEqual(old.pk, new.pk)
        self.assertEqual(Application.objects.filter(recruitment=r, applicant=self.a).count(), 2)
        self.assertEqual(Notification.objects.filter(type=types.APPLICATION_SUBMITTED).count(), 2)

    def test_expired_apply_commits_close_but_cleans_upload(self):
        r = _publish(self.publisher, [self.tag])
        with self.freeze_at(r.deadline), self.assertRaises(BizError) as caught:
            _apply(r, self.a)
        self.assertEqual(caught.exception.code, ErrorCode.RECRUITMENT_NOT_OPEN)
        r.refresh_from_db()
        self.assertEqual((r.status, r.closed_at), ("closed", r.deadline))
        self.assertEqual(Application.objects.count(), 0)
        self.assertEqual(list(self.root.rglob("*.pdf")), [])
        notice = Notification.objects.get(type=types.RECRUITMENT_CLOSED)
        self.assertEqual(notice.recipient_id, self.publisher.pk)

    def test_closed_window_accept_and_exact_expiry(self):
        r = _publish(self.publisher, [self.tag], max_headcount=3)
        a, b = _apply(r, self.a), _apply(r, self.b)
        end = r.deadline + timedelta(days=7)
        with self.freeze_at(end - timedelta(seconds=1)):
            _accept(a, self.publisher)
        self._assert_count_consistent(r)
        self.assertEqual((r.status, r.accepted_count), ("closed", 1))
        with self.freeze_at(end), self.assertRaises(BizError) as caught:
            _accept(b, self.publisher)
        self.assertEqual(caught.exception.code, ErrorCode.PROCESSING_WINDOW_CLOSED)
        b.refresh_from_db()
        self.assertEqual((b.status, b.decided_at), ("rejected", end))
        self._assert_notice(types.APPLICATION_REJECTED, b, self.b)
        self._assert_count_consistent(r)

    def test_publish_requires_active_tags_and_valid_rules(self):
        for tags in ([], [make_tag(active=False)]):
            with self.assertRaises(ValidationFailed):
                _publish(self.publisher, tags)
        for fields in ({"deadline": clock.now()}, {"max_headcount": 0}):
            with self.assertRaises(ValidationFailed):
                _publish(self.publisher, [self.tag], **fields)
        self.assertEqual(Recruitment.objects.count(), 0)
