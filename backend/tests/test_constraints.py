from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.models import User
from apps.applications.models import Application
from apps.audit.models import AuditLog
from apps.chat.models import ChatConversation
from apps.core.clock import now
from apps.notifications.models import EmailLog, Notification
from apps.recruitments.models import Recruitment, RecruitmentTag
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_tag, make_user


class RecruitmentConstraintsTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.publisher = make_user(role="teacher")

    def test_checks(self):
        moment = now()
        cases = [
            ("recruitment_type_chk", {"type": "other"}, {"type": "internship"}),
            ("recruitment_status_chk", {"status": "other"}, {"status": "open"}),
            (
                "recruitment_close_reason_chk",
                {"closed_at": moment, "close_reason": "other"},
                {"closed_at": moment, "close_reason": "manual"},
            ),
            (
                "recruitment_full_chk",
                {"accepted_count": 3},
                {"accepted_count": 3, "status": "full", "full_at": moment},
            ),
            (
                "recruitment_closed_time_chk",
                {"status": "closed"},
                {"status": "closed", "closed_at": moment, "close_reason": "deadline"},
            ),
            (
                "recruitment_full_time_chk",
                {"status": "full"},
                {"status": "full", "full_at": moment},
            ),
            (
                "recruitment_close_pair_chk",
                {"closed_at": moment},
                {"closed_at": moment, "close_reason": "manual"},
            ),
            (
                "recruitment_close_pair_chk",
                {"close_reason": "manual"},
                {"closed_at": None, "close_reason": None},
            ),
            (
                "recruitment_cleanup_pair_chk",
                {"applications_anonymized_at": moment},
                {
                    "applications_anonymized_at": moment,
                    "application_status_counts": {"processing": 0, "accepted": 1, "rejected": 0, "withdrawn": 0, "invalid": 0},
                },
            ),
            (
                "recruitment_cleanup_pair_chk",
                {"application_status_counts": {}},
                {"applications_anonymized_at": None, "application_status_counts": None},
            ),
            (
                "recruitment_max_headcount_chk",
                {"max_headcount": 0, "status": "full", "full_at": moment},
                {"max_headcount": 1},
            ),
            ("recruitment_min_headcount_chk", {"min_headcount": 4}, {"min_headcount": 3}),
            ("recruitment_min_headcount_chk", {"min_headcount": 0}, {"min_headcount": 1}),
            (
                "recruitment_accepted_count_chk",
                {"accepted_count": 4, "status": "full", "full_at": moment},
                {"accepted_count": 2},
            ),
            ("recruitment_accepted_count_chk", {"accepted_count": -1}, {"accepted_count": 0}),
        ]
        for name, invalid, valid in cases:
            with self.subTest(constraint=name, invalid=invalid):
                recruitment = make_recruitment(self.publisher)
                with self.assertRaises(IntegrityError) as caught, transaction.atomic():
                    Recruitment.objects.filter(pk=recruitment.pk).update(**invalid)
                self.assertEqual(caught.exception.__cause__.diag.constraint_name, name)
                Recruitment.objects.filter(pk=recruitment.pk).update(**valid)
                recruitment.refresh_from_db()
                for field, value in valid.items():
                    self.assertEqual(getattr(recruitment, field), value)

    def test_database_does_not_limit_headcount_to_50(self):
        recruitment = make_recruitment(self.publisher, max_headcount=51)
        self.assertEqual(recruitment.max_headcount, 51)

    def test_tag_name_unique(self):
        tag = make_tag(name="计算机")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_tag(name=tag.name)
        self.assertNotEqual(make_tag(name="软件工程").pk, tag.pk)

    def test_recruitment_tag_unique(self):
        recruitment = make_recruitment(self.publisher)
        tag = make_tag()
        RecruitmentTag.objects.create(recruitment=recruitment, tag=tag)
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            RecruitmentTag.objects.create(recruitment=recruitment, tag=tag)
        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            "recruitment_tag_uniq",
        )
        RecruitmentTag.objects.create(recruitment=recruitment, tag=make_tag())
        self.assertEqual(recruitment.tags.count(), 2)


class ApplicationConstraintsTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.recruitment = make_recruitment(make_user(role="teacher"))
        self.applicant = make_user()

    def test_checks(self):
        cases = [
            (
                "application_status_chk",
                # 带 decided_at，避免 application_decided_chk 抢先触发。
                {"status": "other", "decided_at": now()},
                {"status": "rejected", "decided_at": now()},
            ),
            (
                "application_publisher_mark_chk",
                {"publisher_mark": "other"},
                {"publisher_mark": "hold"},
            ),
            ("application_resume_type_chk", {"resume_type": "txt"}, {"resume_type": "docx"}),
            ("application_resume_size_chk", {"resume_size": 10485761}, {"resume_size": 10485760}),
            ("application_decided_chk", {"decided_at": now()}, {"decided_at": None}),
            (
                "application_decided_chk",
                {"status": "accepted"},
                {"status": "accepted", "decided_at": now()},
            ),
        ]
        for name, invalid, valid in cases:
            with self.subTest(constraint=name):
                application = make_application(self.recruitment, make_user())
                with self.assertRaises(IntegrityError) as caught, transaction.atomic():
                    Application.objects.filter(pk=application.pk).update(**invalid)
                self.assertEqual(caught.exception.__cause__.diag.constraint_name, name)
                Application.objects.filter(pk=application.pk).update(**valid)
                application.refresh_from_db()
                for field, value in valid.items():
                    self.assertEqual(getattr(application, field), value)

    def test_negative_resume_size_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_application(self.recruitment, self.applicant, resume_size=-1)
        self.assertEqual(
            make_application(
                self.recruitment,
                self.applicant,
                resume_size=0,
            ).resume_size,
            0,
        )

    def test_only_one_non_withdrawn_application(self):
        for status in ("processing", "accepted", "rejected", "invalid"):
            with self.subTest(status=status):
                applicant = make_user()
                make_application(self.recruitment, applicant, status=status)
                with self.assertRaises(IntegrityError) as caught, transaction.atomic():
                    make_application(self.recruitment, applicant)
                self.assertEqual(
                    caught.exception.__cause__.diag.constraint_name,
                    "application_active_uniq",
                )

    def test_withdrawn_allows_reapplication(self):
        make_application(self.recruitment, self.applicant, status="withdrawn")
        make_application(self.recruitment, self.applicant, status="withdrawn")
        make_application(self.recruitment, self.applicant)
        self.assertEqual(
            Application.objects.filter(applicant=self.applicant).count(),
            3,
        )

    def test_all_terminal_states_have_decision_time(self):
        for status in ("accepted", "rejected", "withdrawn", "invalid"):
            with self.subTest(status=status):
                application = make_application(
                    self.recruitment,
                    make_user(),
                    status=status,
                )
                self.assertIsNotNone(application.decided_at)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Application.objects.filter(pk=application.pk).update(
                        decided_at=None,
                    )


class UserConstraintsTest(TxTestCase):
    def test_login_method(self):
        user = make_user()
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            User.objects.filter(pk=user.pk).update(password="", sso_subject=None)
        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            "user_login_method_chk",
        )
        User.objects.filter(pk=user.pk).update(password="", sso_subject="sso-user")
        User.objects.filter(pk=user.pk).update(password="hash", sso_subject=None)

    def test_case_insensitive_email_unique(self):
        make_user(email="A@x.com")
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            make_user(email="a@x.com")
        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            "user_email_lower_uniq",
        )
        self.assertIsNotNone(make_user(email="b@x.com").pk)

    def test_role(self):
        user = make_user()
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            User.objects.filter(pk=user.pk).update(role="admin")
        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            "user_role_chk",
        )
        User.objects.filter(pk=user.pk).update(role="teacher")

    def test_sso_subject_unique_but_nullable(self):
        first = make_user()
        second = make_user()
        User.objects.filter(pk=first.pk).update(sso_subject="same-subject")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=second.pk).update(sso_subject="same-subject")
        User.objects.filter(pk=second.pk).update(sso_subject="other-subject")

    def test_uid_and_real_id_unique(self):
        first = make_user()
        second = make_user()
        for field in ("uid", "real_id"):
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    User.objects.filter(pk=second.pk).update(**{field: getattr(first, field)})
        self.assertNotEqual(first.uid, second.uid)
        self.assertNotEqual(first.real_id, second.real_id)


class NotificationConstraintsTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.notification = Notification.objects.create(
            recipient=make_user(), type="future_notification", title="标题", content="内容",
        )

    def test_notification_type_can_expand_without_migration(self):
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.type, "future_notification")
        self.assertIsNone(self.notification.recruitment_id)
        self.assertIsNone(self.notification.application_id)

    def test_email_attempts(self):
        for invalid in (-1, 4):
            with self.subTest(attempts=invalid):
                with self.assertRaises(IntegrityError) as caught, transaction.atomic():
                    EmailLog.objects.create(
                        notification=self.notification,
                        to_email="a@x.com",
                        attempts=invalid,
                    )
                self.assertEqual(
                    caught.exception.__cause__.diag.constraint_name,
                    "email_log_attempts_chk",
                )
        for valid in (0, 3):
            log = EmailLog.objects.create(
                notification=self.notification,
                to_email="a@x.com",
                attempts=valid,
            )
            self.assertEqual(log.attempts, valid)

    def test_email_status(self):
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            EmailLog.objects.create(
                notification=self.notification,
                to_email="a@x.com",
                status="other",
            )
        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            "email_log_status_chk",
        )
        for status in ("pending", "sent", "failed"):
            log = EmailLog.objects.create(
                notification=self.notification,
                to_email="a@x.com",
                status=status,
            )
            self.assertEqual(log.status, status)


class AuditConstraintsTest(TxTestCase):
    def test_actor_triple(self):
        user = make_user()
        for actor in (None, user):
            for role in (None, "student"):
                for is_admin in (None, False):
                    fields = {"actor": actor, "actor_role": role, "actor_is_admin": is_admin}
                    with self.subTest(**fields):
                        if (actor is None) == (role is None) == (is_admin is None):
                            log = AuditLog.objects.create(
                                action="permission_denied",
                                target_type="request",
                                **fields,
                            )
                            self.assertIsNotNone(log.pk)
                        else:
                            with self.assertRaises(
                                IntegrityError,
                            ) as caught, transaction.atomic():
                                AuditLog.objects.create(
                                    action="permission_denied",
                                    target_type="request",
                                    **fields,
                                )
                            self.assertEqual(
                                caught.exception.__cause__.diag.constraint_name,
                                "audit_actor_triple_chk",
                            )

    def test_instance_cannot_be_updated_or_deleted(self):
        log = AuditLog.objects.create(action="permission_denied", target_type="request")
        log.reason = "修改"
        with self.assertRaises(RuntimeError):
            log.save()
        with self.assertRaises(RuntimeError):
            log.delete()
        log.refresh_from_db()
        self.assertIsNone(log.reason)

    def test_new_instance_with_existing_pk_cannot_overwrite(self):
        log = AuditLog.objects.create(action="permission_denied", target_type="request")
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditLog(id=log.pk, action="changed", target_type="request").save()
        log.refresh_from_db()
        self.assertEqual(log.action, "permission_denied")


class ProtectedForeignKeyTest(TxTestCase):
    def test_referenced_rows_cannot_be_deleted(self):
        publisher = make_user(role="teacher")
        applicant = make_user()
        recruitment = make_recruitment(publisher)
        tag = make_tag()
        RecruitmentTag.objects.create(recruitment=recruitment, tag=tag)
        application = make_application(recruitment, applicant)
        notification = Notification.objects.create(
            recipient=applicant,
            type="t",
            title="标题",
            content="内容",
            recruitment=recruitment,
            application=application,
        )
        EmailLog.objects.create(notification=notification, to_email="a@x.com")
        AuditLog.objects.create(
            actor=publisher,
            actor_role="teacher",
            actor_is_admin=False,
            action="a",
            target_type="request",
        )
        low, high = sorted([publisher, applicant], key=lambda user: user.pk)
        conversation = ChatConversation.objects.create(user_low=low, user_high=high)
        conversation.messages.create(sender=low, content="hi")

        for obj in (
            publisher,
            applicant,
            recruitment,
            tag,
            application,
            notification,
            conversation,
        ):
            with self.subTest(obj=repr(obj)):
                with self.assertRaises(ProtectedError), transaction.atomic():
                    obj.delete()
                type(obj).objects.get(pk=obj.pk)


class ChatConstraintsTest(TxTestCase):
    def setUp(self):
        super().setUp()
        self.low, self.high = sorted(
            [make_user(), make_user()],
            key=lambda user: user.pk,
        )

    def test_order(self):
        for low, high in ((self.low, self.low), (self.high, self.low)):
            with self.subTest(low=low.pk, high=high.pk):
                with self.assertRaises(IntegrityError) as caught, transaction.atomic():
                    ChatConversation.objects.create(user_low=low, user_high=high)
                self.assertEqual(
                    caught.exception.__cause__.diag.constraint_name,
                    "chat_conversation_order_chk",
                )
        self.assertIsNotNone(
            ChatConversation.objects.create(user_low=self.low, user_high=self.high).pk,
        )

    def test_unique_pair(self):
        ChatConversation.objects.create(user_low=self.low, user_high=self.high)
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            ChatConversation.objects.create(user_low=self.low, user_high=self.high)
        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            "chat_conversation_users_uniq",
        )
        other = make_user()
        ChatConversation.objects.create(user_low=self.low, user_high=other)
