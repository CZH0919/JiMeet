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

    简历路径不使用 MEDIA_ROOT，禁止生成公开 URL；后续文件服务负责生成
    独立存储名、校验上传并在权限检查通过后读取文件。
    """

    @property
    def base_location(self):
        """返回当前配置的私有目录，支持测试临时覆盖配置。"""
        return settings.PRIVATE_FILE_ROOT

    @property
    def location(self):
        """返回私有根目录的绝对路径，不缓存测试覆盖前的配置。"""
        return os.path.abspath(self.base_location)

    def url(self, name):
        """
        拒绝生成简历的公开访问地址。

        Params:
            name: 文件在私有目录内的相对存储名

        Raises:
            ValueError: 简历必须通过有权限校验的下载接口读取
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
