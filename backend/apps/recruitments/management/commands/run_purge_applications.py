"""执行到期申请清理并重试未删除的简历文件。"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef, Q

from apps.applications.models import Application, ResumeRemoval
from apps.core import clock
from apps.notifications import types
from apps.notifications.models import Notification
from apps.recruitments.lifecycle import expired_recruitments
from apps.recruitments.models import Recruitment
from apps.recruitments.retention import purge_expired_applications, remove_files


class Command(BaseCommand):
    help = "汇总满 180 天的申请，移除明细并重试私有文件删除"

    def handle(self, *args, **options):
        moment = clock.now()
        jobs = Recruitment.objects.filter(expired_recruitments(moment)).filter(
            Q(applications_anonymized_at__isnull=True)
            | Exists(Application.objects.filter(recruitment_id=OuterRef("pk")))
            | Exists(Notification.objects.filter(recruitment_id=OuterRef("pk"), type__in=types.APPLICATION_RETENTION_EVENTS))
        ).order_by("pk").values_list("pk", flat=True)
        completed = sum(purge_expired_applications(pk, now=moment) for pk in jobs.iterator(chunk_size=200))
        remove_files(ResumeRemoval.objects.order_by("pk").values_list("path", flat=True).iterator(chunk_size=200))
        pending = ResumeRemoval.objects.count()
        self.stdout.write(f"已汇总 {completed} 条招聘，待重试文件 {pending} 个")
        if pending:
            raise CommandError("仍有私有文件待重试")
