from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from apps.core.choices import EmailStatus


class Notification(models.Model):
    """
    站内通知模型，对应 database.md 1.5 的 notification 表。

    ### Attributes
    - `recipient`: 通知接收人
    - `type`: 由应用层常量维护的通知类型，有意不加数据库 CHECK
    - `title` / `content`: 标题与正文，不应包含简历内容及完整个人信息
    - `recruitment` / `application`: 可空的关联对象，供跳转及留存清理使用
    - `is_read` / `created_at`: 已读标记与创建时间

    申请事件同时填写招聘与申请由后续通知 service 保证，外键统一使用 PROTECT。
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notifications",
        verbose_name="接收人",
    )
    type = models.CharField("通知类型", max_length=32)
    title = models.CharField("标题", max_length=100)
    content = models.TextField("内容")
    recruitment = models.ForeignKey(
        "recruitments.Recruitment",
        on_delete=models.PROTECT,
        related_name="notifications",
        verbose_name="关联招聘",
        null=True,
        blank=True,
    )
    application = models.ForeignKey(
        "applications.Application",
        on_delete=models.PROTECT,
        related_name="notifications",
        verbose_name="关联申请",
        null=True,
        blank=True,
    )
    is_read = models.BooleanField("已读", default=False, db_default=False)
    created_at = models.DateTimeField("创建时间", db_default=Now())

    class Meta:
        db_table = "notification"
        indexes = [
            models.Index(
                fields=["recipient", "is_read", "-created_at"],
                name="notification_recipient_idx",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的通知标识，避免输出正文。"""
        return f"Notification({self.pk})"


class EmailLog(models.Model):
    """
    邮件发送日志模型，对应 database.md 1.6 的 email_log 表。

    ### Attributes
    - `notification`: 对应的站内通知，清理通知前需先显式清理邮件记录
    - `to_email`: 创建记录时的收件地址
    - `status`: pending、sent 或 failed
    - `attempts`: 发送轮次，首次为 0，三次重试为 1～3，最多发送四次
    - `last_error`: 可空的最近失败原因，不保存简历、认证凭证及完整正文
    - `created_at` / `updated_at`: 创建时间与最近修改时间
    """

    notification = models.ForeignKey(
        Notification,
        on_delete=models.PROTECT,
        related_name="email_logs",
        verbose_name="站内通知",
    )
    to_email = models.EmailField("收件地址", max_length=254)
    status = models.CharField(
        "发送状态",
        max_length=16,
        choices=EmailStatus.choices,
        default=EmailStatus.PENDING,
        db_default=EmailStatus.PENDING,
    )
    attempts = models.IntegerField("发送轮次", default=0, db_default=0)
    last_error = models.TextField("最近失败原因", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", db_default=Now())
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "email_log"
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=EmailStatus.values),
                name="email_log_status_chk",
            ),
            models.CheckConstraint(
                condition=Q(attempts__gte=0, attempts__lte=3),
                name="email_log_attempts_chk",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的邮件记录标识。"""
        return f"EmailLog({self.pk})"
