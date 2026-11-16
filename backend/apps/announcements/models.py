from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from apps.core.choices import AnnouncementTimeKind


class Announcement(models.Model):
    """
    竞赛与活动公告模型，对应 database.md 1.9 的 announcement 表。

    ### Attributes
    - `author`: 发布公告的管理员，删除用户时受 PROTECT 保护
    - `title` / `content`: 竞赛或活动名称与正文（含报名方式等其他信息）
    - `time_kind` / `event_at`: 时间类型（报名截止或活动时间）及对应时间，均必填
    - `link_url`: 可空的相关网站，格式由应用层校验
    - `recruitment`: 可空的关联招募，作为招募链接，PROTECT
    - `is_pinned`: 是否置顶，随编辑接口修改
    - `created_at` / `updated_at` / `deleted_at`: 发布、最近编辑与软删除时间

    权限（发布、编辑、删除、置顶）由应用层校验，数据库只保证时间类型取值。
    """

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="announcements",
        verbose_name="发布者",
        db_index=False,
    )
    title = models.CharField("标题", max_length=100)
    content = models.TextField("正文")
    time_kind = models.CharField(
        "时间类型", max_length=16, choices=AnnouncementTimeKind.choices
    )
    event_at = models.DateTimeField("时间")
    link_url = models.CharField("相关网站", max_length=500, null=True, blank=True)
    recruitment = models.ForeignKey(
        "recruitments.Recruitment",
        on_delete=models.PROTECT,
        related_name="announcements",
        verbose_name="关联招募",
        null=True,
        blank=True,
        db_index=False,
    )
    is_pinned = models.BooleanField("置顶", default=False, db_default=False)
    created_at = models.DateTimeField("发布时间", db_default=Now())
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    deleted_at = models.DateTimeField("软删除时间", null=True, blank=True)

    class Meta:
        db_table = "announcement"
        verbose_name = "公告"
        verbose_name_plural = "公告"
        constraints = [
            models.CheckConstraint(
                condition=Q(time_kind__in=AnnouncementTimeKind.values),
                name="announcement_time_kind_chk",
            ),
        ]
        indexes = [
            models.Index(
                fields=["-is_pinned", "-created_at"],
                condition=Q(deleted_at__isnull=True),
                name="announcement_list_idx",
            ),
            models.Index(
                fields=["recruitment"],
                condition=Q(recruitment__isnull=False),
                name="announcement_recruitment_idx",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的标识。"""
        return f"Announcement({self.pk})"
