from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now

from apps.core.choices import CloseReason, RecruitmentStatus, RecruitmentType


class Recruitment(models.Model):
    """
    招聘信息模型，对应 database.md 1.2 的 recruitment 表。

    ### Attributes
    - `publisher`: 发布者，删除用户时受 PROTECT 保护
    - `title` / `type` / `description`: 招聘名称、类型和需求描述
    - `min_headcount` / `max_headcount`: 展示人数下限与实际接受人数上限
    - `accepted_count`: 历史累计接受人数，删除或清理申请时不递减
    - `status` / `deadline`: 当前状态与投递截止时间
    - `closed_at` / `close_reason`: 首次关闭时间及原因，必须同时存在或为空
    - `full_at` / `deleted_at`: 首次满员时间与软删除时间
    - `application_status_counts` / `applications_anonymized_at`: 留存清理后的
      状态计数及完成时间，必须同时存在或为空
    - `tags`: 通过 RecruitmentTag 关联的领域标签
    - `created_at` / `updated_at`: 发布时间与最近修改时间

    数据库保证人数范围及状态与时间的对应关系；截止时间和人数 50 上限
    由应用层校验，状态流转由后续 service 在招聘行锁内执行。
    """

    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recruitments",
        verbose_name="发布者", db_index=False,
    )
    title = models.CharField("招募名称", max_length=100)
    type = models.CharField("类型", max_length=32, choices=RecruitmentType.choices)
    description = models.TextField("需求描述")
    min_headcount = models.IntegerField("人数下限", null=True, blank=True)
    max_headcount = models.IntegerField("人数上限")
    accepted_count = models.IntegerField("累计接受人数", default=0, db_default=0)
    status = models.CharField(
        "状态", max_length=16, choices=RecruitmentStatus.choices,
        default=RecruitmentStatus.OPEN, db_default=RecruitmentStatus.OPEN,
    )
    deadline = models.DateTimeField("截止时间")
    closed_at = models.DateTimeField("首次关闭时间", null=True, blank=True)
    full_at = models.DateTimeField("首次满员时间", null=True, blank=True)
    close_reason = models.CharField(
        "关闭原因", max_length=16, choices=CloseReason.choices, null=True, blank=True,
    )
    deleted_at = models.DateTimeField("软删除时间", null=True, blank=True)
    application_status_counts = models.JSONField("申请状态统计", null=True, blank=True)
    applications_anonymized_at = models.DateTimeField("申请清理完成时间", null=True, blank=True)
    created_at = models.DateTimeField("发布时间", db_default=Now())
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    tags = models.ManyToManyField(
        "Tag", through="RecruitmentTag", related_name="recruitments", verbose_name="领域标签",
    )

    class Meta:
        db_table = "recruitment"
        verbose_name = "招聘"
        verbose_name_plural = "招聘"
        constraints = [
            models.CheckConstraint(
                condition=Q(type__in=RecruitmentType.values),
                name="recruitment_type_chk",
            ),
            models.CheckConstraint(
                condition=Q(status__in=RecruitmentStatus.values),
                name="recruitment_status_chk",
            ),
            models.CheckConstraint(
                condition=Q(close_reason__isnull=True) | Q(close_reason__in=CloseReason.values),
                name="recruitment_close_reason_chk",
            ),
            models.CheckConstraint(
                condition=Q(max_headcount__gte=1),
                name="recruitment_max_headcount_chk",
            ),
            models.CheckConstraint(
                condition=(
                    Q(min_headcount__isnull=True)
                    | Q(min_headcount__gte=1, min_headcount__lte=F("max_headcount"))
                ),
                name="recruitment_min_headcount_chk",
            ),
            models.CheckConstraint(
                condition=Q(
                    accepted_count__gte=0,
                    accepted_count__lte=F("max_headcount"),
                ),
                name="recruitment_accepted_count_chk",
            ),
            models.CheckConstraint(
                condition=Q(accepted_count__lt=F("max_headcount")) | Q(status="full"),
                name="recruitment_full_chk",
            ),
            models.CheckConstraint(
                condition=~Q(status="closed") | Q(closed_at__isnull=False),
                name="recruitment_closed_time_chk",
            ),
            models.CheckConstraint(
                condition=~Q(status="full") | Q(full_at__isnull=False),
                name="recruitment_full_time_chk",
            ),
            models.CheckConstraint(
                condition=(
                    Q(closed_at__isnull=True, close_reason__isnull=True)
                    | Q(closed_at__isnull=False, close_reason__isnull=False)
                ),
                name="recruitment_close_pair_chk",
            ),
            models.CheckConstraint(
                condition=(
                    Q(applications_anonymized_at__isnull=True, application_status_counts__isnull=True)
                    | Q(applications_anonymized_at__isnull=False, application_status_counts__isnull=False)
                ),
                name="recruitment_cleanup_pair_chk",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "-created_at"],
                condition=Q(deleted_at__isnull=True),
                name="recruitment_status_created_idx",
            ),
            models.Index(fields=["publisher"], name="recruitment_publisher_idx"),
            models.Index(
                fields=["deadline"],
                condition=Q(status="open", deleted_at__isnull=True),
                name="recruitment_deadline_idx",
            ),
            models.Index(
                fields=["closed_at"],
                condition=Q(status="closed", deleted_at__isnull=True),
                name="recruitment_closed_at_idx",
            ),
            models.Index(
                fields=["id"],
                condition=Q(applications_anonymized_at__isnull=True) & (
                    Q(closed_at__isnull=False)
                    | Q(full_at__isnull=False)
                    | Q(deleted_at__isnull=False)
                ),
                name="recruitment_cleanup_idx",
            ),
            GinIndex(
                fields=["title"],
                opclasses=["gin_trgm_ops"],
                name="recruitment_title_trgm",
            ),
            GinIndex(
                fields=["description"],
                opclasses=["gin_trgm_ops"],
                name="recruitment_description_trgm",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的标识，避免输出招聘内容。"""
        return f"Recruitment({self.pk})"


class Tag(models.Model):
    """
    领域标签模型，对应 database.md 1.3 的 tag 表。

    ### Attributes
    - `name`: 唯一的领域名称
    - `sort_order`: 前端展示顺序，默认 0
    - `is_active`: 是否可供新招聘选择，停用不影响已有招聘关联
    """

    name = models.CharField("标签名称", max_length=32, unique=True)
    sort_order = models.IntegerField("展示顺序", default=0, db_default=0)
    is_active = models.BooleanField("启用", default=True, db_default=True)

    class Meta:
        db_table = "tag"
        verbose_name = "领域标签"
        verbose_name_plural = "领域标签"

    def __str__(self) -> str:
        """返回仅含数据库主键的标签标识。"""
        return f"Tag({self.pk})"


class RecruitmentTag(models.Model):
    """
    招聘与领域标签的显式关联模型，对应 recruitment_tag 表。

    `recruitment` 和 `tag` 均使用 PROTECT 外键，同一对招聘与标签只能关联一次。
    发布时至少选择一个标签的要求由应用层保证。
    """

    recruitment = models.ForeignKey(
        Recruitment,
        on_delete=models.PROTECT,
        related_name="recruitment_tags",
        verbose_name="招聘",
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.PROTECT,
        related_name="recruitment_tags",
        verbose_name="领域标签",
    )

    class Meta:
        db_table = "recruitment_tag"
        constraints = [
            models.UniqueConstraint(
                fields=["recruitment", "tag"],
                name="recruitment_tag_uniq",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的关联标识。"""
        return f"RecruitmentTag({self.pk})"
