import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now
from django.utils.deconstruct import deconstructible

from apps.core.choices import ApplicationStatus, PublisherMark, ResumeType
from apps.core.indexes import PostgreSQLIndex


@deconstructible
class PrivateResumeStorage(FileSystemStorage):
    """
    简历专用本地存储，根目录随 settings.PRIVATE_FILE_ROOT 读取。

    简历路径不使用 MEDIA_ROOT，禁止生成公开 URL；文件服务负责生成
    独立存储名、校验上传并在权限检查通过后读取文件。
    """

    @property
    def base_location(self):
        """读取当前配置的私有存储根目录。

        Returns:
            Path: settings.PRIVATE_FILE_ROOT，支持环境或测试覆盖。
        """
        return settings.PRIVATE_FILE_ROOT

    @property
    def location(self):
        """返回私有存储根目录的绝对路径。

        Returns:
            str: 根据当前配置计算的绝对路径，不缓存旧配置。
        """
        return os.path.abspath(self.base_location)

    def url(self, name):
        """拒绝为私有简历生成公开地址。

        Args:
            name: 文件相对存储名，当前实现不使用该值。

        Raises:
            ValueError: 调用始终被拒绝，简历只能通过鉴权下载接口访问。
        """
        raise ValueError("私有简历不提供公开 URL")


class Application(models.Model):
    """
    申请模型，对应 database.md 1.4 的 application 表。

    ### Attributes
    - `recruitment` / `applicant`: 所属招聘与申请人，均不可为空
    - `resume_file` / `resume_name`: 私有简历路径与仅用于展示的原始文件名
    - `resume_size` / `resume_type`: 文件字节数（最多 10MB）与 pdf/doc/docx 格式
    - `note`: 可空的补充说明
    - `status`: 处理状态，同人同招聘最多一条未撤回申请
    - `publisher_mark`: 仅发布者可见的暂留标记，独立于申请状态
    - `has_unseen_update`: 申请人修改后供发布者查看的小红点标记
    - `decided_at`: 首次离开 processing 的时间，processing 时必须为空
    - `created_at` / `updated_at`: 提交时间与最近修改时间

    accepted 转 invalid 时保留首次决定时间；访问权限及状态流转由应用层校验。
    """

    recruitment = models.ForeignKey(
        "recruitments.Recruitment",
        on_delete=models.PROTECT,
        related_name="applications",
        verbose_name="招聘",
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="applications",
        verbose_name="申请人",
    )
    resume_file = models.FileField(
        "简历路径",
        max_length=255,
        storage=PrivateResumeStorage(),
    )
    resume_name = models.CharField("原始文件名", max_length=255)
    resume_size = models.PositiveIntegerField("简历大小")
    resume_type = models.CharField("简历格式", max_length=8, choices=ResumeType.choices)
    note = models.TextField("补充说明", null=True, blank=True)
    status = models.CharField(
        "状态",
        max_length=16,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PROCESSING,
        db_default=ApplicationStatus.PROCESSING,
    )
    publisher_mark = models.CharField(
        "发布者标记",
        max_length=16,
        choices=PublisherMark.choices,
        default=PublisherMark.NONE,
        db_default=PublisherMark.NONE,
    )
    has_unseen_update = models.BooleanField("有未读修改", default=False, db_default=False)
    created_at = models.DateTimeField("提交时间", db_default=Now())
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    decided_at = models.DateTimeField("首次决定时间", null=True, blank=True)

    class Meta:
        db_table = "application"
        verbose_name = "申请"
        verbose_name_plural = "申请"
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ApplicationStatus.values),
                name="application_status_chk",
            ),
            models.CheckConstraint(
                condition=Q(publisher_mark__in=PublisherMark.values),
                name="application_publisher_mark_chk",
            ),
            models.CheckConstraint(
                condition=Q(resume_type__in=ResumeType.values),
                name="application_resume_type_chk",
            ),
            models.CheckConstraint(
                condition=Q(resume_size__lte=10485760),
                name="application_resume_size_chk",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="processing", decided_at__isnull=True)
                    | (~Q(status="processing") & Q(decided_at__isnull=False))
                ),
                name="application_decided_chk",
            ),
            models.UniqueConstraint(
                fields=["recruitment", "applicant"],
                condition=~Q(status="withdrawn"),
                name="application_active_uniq",
            ),
        ]
        indexes = [
            PostgreSQLIndex(
                fields=["recruitment", "status"],
                name="application_recruitment_status_idx",
            ),
            models.Index(
                fields=["applicant", "-created_at"],
                name="application_applicant_idx",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的申请标识，避免输出申请内容。"""
        return f"Application({self.pk})"


class ApplicationHistoryReason(models.TextChoices):
    ACCEPT = "accept", "接受"
    REJECT_MANUAL = "reject_manual", "主动拒绝"
    WITHDRAW = "withdraw", "撤回"
    AUTO_FULL = "auto_full", "满员自动拒绝"
    AUTO_WINDOW = "auto_window", "处理期限届满"
    DELETE_INVALID = "delete_invalid", "招聘删除失效"


class ApplicationStatusHistory(models.Model):
    """仅追加的申请状态变更记录；旧记录不回填推测事件。

    occurred_at 为业务生效时间，created_at 为实际记录时间；补执行事件可不同。
    actor 为空表示系统自动处理，不保存说明、简历或认证信息。
    """

    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="status_history")
    recruitment = models.ForeignKey("recruitments.Recruitment", on_delete=models.PROTECT, related_name="application_history")
    from_status = models.CharField("原状态", max_length=16, choices=ApplicationStatus.choices)
    to_status = models.CharField("目标状态", max_length=16, choices=ApplicationStatus.choices)
    reason = models.CharField("变更原因", max_length=32, choices=ApplicationHistoryReason.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="application_actions")
    occurred_at = models.DateTimeField("业务生效时间")
    created_at = models.DateTimeField("记录时间", db_default=Now())

    class Meta:
        db_table = "application_status_history"
        ordering = ["occurred_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(from_status="processing", to_status="accepted", reason="accept")
                    | Q(from_status="processing", to_status="rejected", reason__in=["reject_manual", "auto_full", "auto_window"])
                    | Q(from_status="processing", to_status="withdrawn", reason="withdraw")
                    | Q(from_status__in=["processing", "accepted"], to_status="invalid", reason="delete_invalid")
                ),
                name="app_history_transition_chk",
            ),
            models.CheckConstraint(
                condition=(
                    Q(reason__in=["auto_full", "auto_window"], actor__isnull=True)
                    | (Q(reason__in=["accept", "reject_manual", "withdraw", "delete_invalid"]) & Q(actor__isnull=False))
                ),
                name="app_history_actor_chk",
            ),
            models.UniqueConstraint(fields=["application", "from_status", "to_status"], name="app_history_transition_uniq"),
        ]
        indexes = [models.Index(fields=["application", "occurred_at"], name="app_history_time_idx")]
