from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from apps.core.choices import AnnouncementTimeKind


class Announcement(models.Model):
    """
    竞赛与活动公告模型，对应 database.md 1.9 的 announcement 表。

    ### Attributes
    - `author`: 发布公告的管理员（直接发布或审核通过的审核人），删除用户时受 PROTECT 保护
    - `submitted_by`: 可空的投稿人；仅审核通过的公告填写，直接发布与历史公告为空
    - `title` / `content`: 竞赛或活动名称与正文（含报名方式等其他信息）
    - `time_kind` / `event_at`: 时间类型（报名截止或活动时间）及对应时间，均必填
    - `link_url`: 可空的相关网站，格式由应用层校验
    - `recruitment`: 可空的关联招募，作为招募链接，PROTECT
    - `is_pinned`: 保留字段，本轮 HTTP 不提供置顶能力
    - `created_at` / `updated_at` / `deleted_at`: 发布、最近编辑与软删除时间

    权限（发布、删除）由应用层校验，数据库只保证时间类型取值；
    Sprint3 起公告不可编辑（编辑入口已收回）。
    """

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="announcements",
        verbose_name="发布者",
        db_index=False,
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_announcements",
        verbose_name="投稿人",
        null=True,
        blank=True,
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


class AnnouncementSubmission(models.Model):
    """
    公告投稿（待审稿）模型，对应 FR-09 的投稿、审核流程。

    ### Attributes
    - `submitter`: 投稿人（普通用户或管理员均可投稿）
    - `title` / `content` / `time_kind` / `event_at` / `link_url`: 与公告同口径的投稿内容，
      提交后不可改稿、不可撤回
    - `status`: pending 待审核 / approved 已通过 / rejected 已驳回
    - `claimed_by` / `claimed_until`: 领取审核的管理员与到期时间（15 分钟），
      到期或主动交回后其他管理员可接手
    - `reviewed_by` / `reviewed_at` / `reject_reason`: 审核管理员、审核时间与驳回理由
    - `announcement`: 可空，审核通过后按投稿原文生成的正式公告（PROTECT）
    - `submitted_at`: 提交时间，用于每日额度与逾期判断
    """

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="announcement_submissions",
        verbose_name="投稿人",
    )
    title = models.CharField("标题", max_length=100)
    content = models.TextField("正文")
    time_kind = models.CharField(
        "时间类型", max_length=16, choices=AnnouncementTimeKind.choices
    )
    event_at = models.DateTimeField("时间")
    link_url = models.CharField("相关网站", max_length=500, null=True, blank=True)
    status = models.CharField("状态", max_length=16, default=STATUS_PENDING)
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="claimed_announcement_submissions",
        verbose_name="领取人",
        null=True,
        blank=True,
    )
    claimed_until = models.DateTimeField("领取到期时间", null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_announcement_submissions",
        verbose_name="审核人",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField("审核时间", null=True, blank=True)
    reject_reason = models.TextField("驳回理由", null=True, blank=True)
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.PROTECT,
        related_name="submission",
        verbose_name="生成公告",
        null=True,
        blank=True,
    )
    submitted_at = models.DateTimeField("提交时间", db_default=Now())

    class Meta:
        db_table = "announcement_submission"
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected"]),
                name="announcement_submission_status_chk",
            ),
            models.CheckConstraint(
                condition=Q(time_kind__in=AnnouncementTimeKind.values),
                name="announcement_submission_time_kind_chk",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(status="pending") & Q(reviewed_at__isnull=True) & Q(announcement__isnull=True))
                    | (Q(status="approved") & Q(reviewed_at__isnull=False) & Q(announcement__isnull=False))
                    | (Q(status="rejected") & Q(reviewed_at__isnull=False) & Q(announcement__isnull=True)
                       & Q(reject_reason__isnull=False))
                ),
                name="announcement_submission_state_chk",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "submitted_at"], name="ann_sub_queue_idx"),
            models.Index(fields=["submitter", "-submitted_at"], name="ann_sub_mine_idx"),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的标识。"""
        return f"AnnouncementSubmission({self.pk})"
