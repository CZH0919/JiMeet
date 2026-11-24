"""历史审计升级时保留业务原因，移除旧管理命令自动写入的邮箱。"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.audit.models import AuditLog
from tests.base import TxTestCase
from tests.factories import make_user


class AuditLifecycleMigrationTest(TxTestCase):
    def test_old_command_reason_and_actor_snapshot(self):
        user = make_user()
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        previous = [("audit", "0001_initial")]
        executor.migrate(previous)
        old = executor.loader.project_state(previous).apps.get_model("audit", "AuditLog")
        fields = dict(actor_id=user.pk, actor_role="student", actor_is_admin=False, target_type="user", target_id=user.pk)
        historic = old.objects.create(**fields, action="admin_grant", reason="管理命令授予管理员权限（目标 " + user.email + "）")
        other = old.objects.create(**fields, action="permission_denied", reason="需要管理员权限")
        MigrationExecutor(connection).migrate(latest)
        item = AuditLog.objects.get(pk=historic.pk)
        self.assertEqual((item.reason, item.actor_id, item.target_id), ("管理命令授予管理员权限", user.pk, user.pk))
        self.assertEqual(AuditLog.objects.get(pk=other.pk).reason, "需要管理员权限")
