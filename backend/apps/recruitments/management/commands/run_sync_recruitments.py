"""逐个招聘补执行到期关闭及七天自动拒绝。"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q

from apps.applications.models import Application
from apps.core import clock
from apps.core.choices import ApplicationStatus, RecruitmentStatus
from apps.recruitments.models import Recruitment
from apps.recruitments.state import sync_recruitment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """复用状态入口，每个招聘独立提交，单项失败不阻断后续招聘。"""

    help = "补执行到期招聘的关闭及七天自动拒绝"

    def handle(self, *args, **options):
        """固定本轮时间，筛选候选并输出成功、失败及状态变更数量。"""
        now = clock.now()
        processing = Application.objects.filter(
            recruitment_id=OuterRef("pk"), status=ApplicationStatus.PROCESSING,
        )
        # 已关闭且没有待处理申请的招聘无需重复扫描；软删除招聘也不参与。
        candidates = Recruitment.objects.filter(deleted_at__isnull=True).annotate(
            has_processing=Exists(processing),
        ).filter(
            Q(status=RecruitmentStatus.OPEN, deadline__lte=now)
            | Q(status=RecruitmentStatus.CLOSED, closed_at__lte=now - timedelta(days=7), has_processing=True)
        ).order_by("pk").values_list("pk", flat=True)
        processed = failed = closed = rejected = 0
        for recruitment_id in candidates.iterator(chunk_size=200):
            try:
                result = sync_recruitment(recruitment_id, now=now)
            except Exception:
                # 记录失败并继续，其事务已由 sync_recruitment 回滚，下一轮可重试。
                logger.exception("招聘状态同步失败", extra={"recruitment_id": recruitment_id})
                failed += 1
                continue
            processed += 1
            closed += int(result.closed)
            rejected += result.auto_rejected
        self.stdout.write(
            f"招聘状态同步完成：处理 {processed} 个，失败 {failed} 个，关闭 {closed} 个，自动拒绝 {rejected} 份申请"
        )
