"""既有删除统计修复与历史记录证据边界的迁移回归。"""
from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.applications.models import ApplicationStatusHistory
from apps.core import clock
from tests.base import TxTestCase


class Stage4MigrationTest(TxTestCase):
    def test_legacy_counts_are_repaired_without_reopening_or_fake_history(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()

        def restore():
            MigrationExecutor(connection).migrate(latest)

        self.addCleanup(restore)
        executor.migrate([("recruitments", "0002_trigram_indexes")])
        state = MigrationExecutor(connection).loader.project_state([("recruitments", "0002_trigram_indexes")])
        User = state.apps.get_model("accounts", "User")
        Recruitment = state.apps.get_model("recruitments", "Recruitment")
        owner = User.objects.create(real_id="migration-user", name="迁移样例", nickname="迁移样例", email="migration@tongji.edu.cn", role="student", password="!")
        before = clock.now() - timedelta(days=20)
        deleted = Recruitment.objects.create(
            publisher=owner, title="历史删除", type="competition", description="保留原始业务时间",
            max_headcount=3, accepted_count=3, status="full", full_at=before,
            deadline=before + timedelta(days=1), deleted_at=before + timedelta(days=2),
        )
        active = Recruitment.objects.create(
            publisher=owner, title="正常招聘", type="competition", description="不属于修复范围",
            max_headcount=5, accepted_count=2, status="open", deadline=clock.now() + timedelta(days=1),
        )
        immutable = (deleted.status, deleted.full_at, deleted.deadline, deleted.deleted_at, deleted.created_at, deleted.updated_at)
        restore()
        deleted.refresh_from_db(); active.refresh_from_db()
        self.assertEqual(deleted.accepted_count, 0)
        self.assertEqual(active.accepted_count, 2)
        self.assertEqual((deleted.status, deleted.full_at, deleted.deadline, deleted.deleted_at, deleted.created_at, deleted.updated_at), immutable)
        self.assertFalse(ApplicationStatusHistory.objects.exists())
        MigrationExecutor(connection).migrate([("recruitments", "0002_trigram_indexes")])
        restore()
        deleted.refresh_from_db()
        self.assertEqual((deleted.accepted_count, deleted.status, deleted.full_at), (0, "full", before))
        self.assertFalse(ApplicationStatusHistory.objects.exists())
