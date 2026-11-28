"""账户核验迁移保留有效邮件挑战，撤销旧版未区分账号状态的注册资格。"""
from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.models import RegistrationVerification
from apps.core import clock
from tests.base import TxTestCase
from tests.factories import make_user


class VerificationMigrationTest(TxTestCase):
    def test_upgrade_expires_ambiguous_grants_and_preserves_codes_and_accounts(self):
        original = make_user(password="Account-fixture!927")
        password_hash = original.password
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        previous = [("accounts", "0004_remove_registrationverification_reg_verify_email_session_uniq_and_more")]
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        mail_request = apps.get_model("accounts", "RegistrationMailRequest")
        verification = apps.get_model("accounts", "RegistrationVerification")
        now = clock.now()
        request = mail_request.objects.create(email_key="a" * 64, ip_key="b" * 64, requested_at=now)
        fields = {"latest_request": request, "email_key": request.email_key}
        grant = verification.objects.create(**fields, session_key_hash="c" * 64, verified_at=now)
        challenge = verification.objects.create(
            **fields, session_key_hash="d" * 64, code_digest="e" * 64, code_expires_at=now + timedelta(minutes=5),
        )
        MigrationExecutor(connection).migrate(latest)
        grant = RegistrationVerification.objects.get(pk=grant.pk)
        self.assertIsNone(grant.verified_at)
        self.assertIsNone(grant.duplicate_verified_at)
        upgraded = RegistrationVerification.objects.get(pk=challenge.pk)
        self.assertEqual((upgraded.code_digest, upgraded.code_expires_at), (challenge.code_digest, challenge.code_expires_at))
        original.refresh_from_db()
        self.assertEqual(original.password, password_hash)
