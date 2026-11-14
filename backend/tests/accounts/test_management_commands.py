"""受控账号命令的事务、并发与密码初始化边界。"""
import io
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connections

from apps.accounts.management.commands.init_password import Command as InitPasswordCommand
from apps.audit import actions
from apps.audit.models import AuditLog
from tests.base import TxTestCase
from tests.factories import make_user


class ManagementCommandBoundaryTest(TxTestCase):
    def _parallel(self, jobs):
        gate = Barrier(len(jobs))

        def run(job):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                return job()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return [future.result(timeout=20) for future in futures]

    def test_audit_failure_rolls_back_all_management_changes(self):
        for command in ("grant_admin", "revoke_admin", "init_password"):
            with self.subTest(command=command):
                user = make_user(is_admin=command == "revoke_admin")
                initial_admin, initial_password = user.is_admin, user.password
                module = "apps.accounts.management.commands." + command
                with mock.patch(module + ".record", side_effect=RuntimeError("audit unavailable")):
                    with mock.patch.object(InitPasswordCommand, "_read_password", return_value="Recovery!4827"):
                        with self.assertRaises(RuntimeError):
                            call_command(command, email=user.email, stdout=io.StringIO())
                user.refresh_from_db()
                self.assertEqual(user.is_admin, initial_admin)
                self.assertTrue(user.password == initial_password)
                self.assertFalse(AuditLog.objects.filter(target_type="user", target_id=user.pk).exists())

    def test_concurrent_grant_and_revoke_are_idempotent(self):
        for command, initial, action in (
            ("grant_admin", False, actions.ADMIN_GRANT),
            ("revoke_admin", True, actions.ADMIN_REVOKE),
        ):
            with self.subTest(command=command):
                user = make_user(is_admin=initial)

                def change():
                    call_command(command, email=user.email, stdout=io.StringIO())

                self._parallel([change, change])
                user.refresh_from_db()
                self.assertEqual(user.is_admin, not initial)
                self.assertEqual(AuditLog.objects.filter(action=action, target_id=user.pk).count(), 1)

    def test_concurrent_password_initialization_allows_one_change(self):
        user = make_user()
        input_gate = Barrier(2)

        def password_input():
            input_gate.wait(timeout=10)
            return "ConcurrentInit!4827"

        def initialize():
            try:
                call_command("init_password", email=user.email, stdout=io.StringIO())
                return "initialized"
            except CommandError:
                return "rejected"

        with mock.patch.object(InitPasswordCommand, "_read_password", side_effect=password_input):
            self.assertEqual(sorted(self._parallel([initialize, initialize])), ["initialized", "rejected"])
        user.refresh_from_db()
        self.assertTrue(user.check_password("ConcurrentInit!4827"))
        self.assertEqual(AuditLog.objects.filter(action=actions.PASSWORD_INIT, target_id=user.pk).count(), 1)

    def test_existing_password_is_not_overwritten_or_prompted(self):
        user = make_user(password="ExistingPass!4827")
        with mock.patch.object(InitPasswordCommand, "_read_password") as read_password:
            with self.assertRaisesMessage(CommandError, "已有可用密码"):
                call_command("init_password", email=user.email, stdout=io.StringIO())
        read_password.assert_not_called()
        user.refresh_from_db()
        self.assertTrue(user.check_password("ExistingPass!4827"))
        self.assertFalse(AuditLog.objects.filter(action=actions.PASSWORD_INIT).exists())

    def test_password_policy_rejects_invalid_lengths_and_similarity(self):
        for password in ("Ax!2937", "Ab!72" * 26, "CedarRiver!5928", "name-similarity"):
            with self.subTest(length=len(password)):
                user = make_user(name="CedarRiver!5928", email="name-similarity@tongji.edu.cn")
                with mock.patch("sys.stdin", io.StringIO(password + "\n")):
                    with self.assertRaisesMessage(CommandError, "密码不合规"):
                        call_command("init_password", email=user.email, stdout=io.StringIO())
                user.refresh_from_db()
                self.assertFalse(user.has_usable_password())
                user.delete()

    def test_password_length_boundaries_can_authenticate(self):
        for password in ("Ax!2937Q", "Az!79" * 25 + "Qx8"):
            with self.subTest(length=len(password)):
                user = make_user()
                with mock.patch("sys.stdin", io.StringIO(password + "\r\n")):
                    call_command("init_password", email=user.email, stdout=io.StringIO())
                from apps.accounts.services import login_with_password

                self.assertEqual(login_with_password(email=user.email, password=password).pk, user.pk)

    def test_terminal_input_uses_non_echo_reader(self):
        user = make_user()
        password = "TerminalPass!4827"
        output = io.StringIO()
        with mock.patch("sys.stdin.isatty", return_value=True):
            with mock.patch("apps.accounts.management.commands.init_password.getpass.getpass", return_value=password) as reader:
                call_command("init_password", email=user.email, stdout=output)
        reader.assert_called_once()
        self.assertNotIn(password, output.getvalue())
        self.assertFalse(AuditLog.objects.filter(reason__contains=password).exists())

    def test_pipe_input_preserves_password_spaces(self):
        user = make_user()
        password = "  PipePass!4827  "
        with mock.patch("sys.stdin", io.StringIO(password + "\r\n")):
            call_command("init_password", email=user.email, stdout=io.StringIO())
        user.refresh_from_db()
        self.assertTrue(user.check_password(password))
        self.assertFalse(user.check_password(password.strip()))
