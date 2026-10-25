from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.files.jobs import cleanup_orphans
from apps.recruitments.retention import purge_expired_applications


class ReservedCommandsTest(SimpleTestCase):
    def test_commands_fail_explicitly(self):
        for name in ("run_purge_applications", "run_send_emails", "run_cleanup_orphan_files", "run_cleanup_audit_logs"):
            with self.subTest(command=name), self.assertRaisesMessage(CommandError, "reserved"):
                call_command(name, stdout=StringIO())

    def test_reserved_functions(self):
        for function in (lambda: purge_expired_applications(1), cleanup_orphans):
            with self.assertRaisesMessage(NotImplementedError, "reserved for week 2"):
                function()
