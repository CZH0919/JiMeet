"""招聘结束后的匿名汇总、关联明细清除与简历删除重试。"""
from functools import partial

from django.db import transaction
from django.db.models import Count

from apps.applications.models import Application, ApplicationStatusHistory, ResumeRemoval
from apps.audit.models import AuditLog
from apps.audit.service import detach_actors
from apps.core import clock
from apps.core.choices import ApplicationStatus
from apps.files.storage import discard_resume
from apps.notifications import types
from apps.notifications.models import EmailLog, Notification
from apps.recruitments.lifecycle import details_expired
from apps.recruitments.models import Recruitment
from apps.recruitments.rules import effective_application_status


def erase_notifications(notifications):
    """先清理持有保护外键的历史邮件，再清除对应通知。"""
    EmailLog.objects.filter(notification__in=notifications).delete()
    notifications.delete()


def remove_files(paths):
    """处理持久化删除任务。文件缺失视为成功，失败的任务留待重试。"""
    for path in paths:
        with transaction.atomic():
            task = ResumeRemoval.objects.select_for_update().filter(path=path).first()
            if task is not None and (Application.objects.filter(resume_file=path).exists() or discard_resume(path)):
                task.delete()


def queue_file_removal(paths):
    """在移除引用的同一事务内登记文件，提交成功后执行首次删除。"""
    ResumeRemoval.objects.bulk_create([ResumeRemoval(path=p) for p in paths], ignore_conflicts=True)
    transaction.on_commit(partial(remove_files, paths), robust=True)


def erase_applications(rows):
    """在招聘锁内移除明细，提交后删除文件；事务回滚时保留文件及原始记录。"""
    paths = list(rows.order_by().values_list("resume_file", flat=True).distinct())
    if not paths:
        return
    queue_file_removal(paths)
    detach_actors(AuditLog.objects.filter(target_type="application", target_id__in=rows.values("pk")))
    erase_notifications(Notification.objects.filter(application__in=rows))
    ApplicationStatusHistory.objects.filter(application__in=rows).delete()
    rows.delete()


def purge_locked(job, moment):
    """在已锁定的招聘上合并匿名计数并清除明细。已有最终快照不重复累加。"""
    if not details_expired(job, moment):
        return False
    if job.status == "open" and job.deleted_at is None and job.deadline <= moment:
        job.status = "closed"
        if job.closed_at is None:
            job.closed_at, job.close_reason = job.deadline, "deadline"
        job.save(update_fields=["status", "closed_at", "close_reason", "updated_at"])
    rows = Application.objects.filter(recruitment=job)
    first = job.applications_anonymized_at is None
    if first:
        counts = {s: job.anonymous_counts.get(s, 0) for s in ApplicationStatus.values}
        for group in rows.values("status").annotate(n=Count("pk")):
            counts[effective_application_status(group["status"], job, moment)] += group["n"]
        job.anonymous_counts = {}
        job.application_status_counts = counts
        job.applications_anonymized_at = moment
        job.save(update_fields=["anonymous_counts", "application_status_counts", "applications_anonymized_at"])
    erase_notifications(Notification.objects.filter(
        recruitment=job, application__isnull=True, type__in=types.APPLICATION_RETENTION_EVENTS,
    ))
    erase_applications(rows)
    return first


def purge_expired_applications(recruitment_id, *, now=None):
    """按招聘独立提交，返回是否首次生成最终统计。"""
    with transaction.atomic():
        job = Recruitment.objects.select_for_update().filter(pk=recruitment_id).first()
        return job is not None and purge_locked(job, now or clock.now())
