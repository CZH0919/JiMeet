from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now


class AuditLog(models.Model):
    """
    只追加的审计日志模型，对应 database.md 1.8 的 audit_log 表。

    ### Attributes
    - `actor` / `actor_role` / `actor_is_admin`: 操作者和操作时的身份快照，
      三者同时为空或同时非空，未登录请求使用全空
    - `action`: 操作名称，由应用层常量约束，有意不加数据库 CHECK
    - `target_type` / `target_id`: 历史对象类型和主键，目标不存在时主键可空，
      target_id 不使用外键，以便申请清理后保留审计记录
    - `reason`: 可空的操作原因，不记录申请正文或认证凭证
    - `created_at`: 日志创建时间，至少留存一年

    模型实例只允许创建，禁止修改和删除；不得通过 QuerySet.update/delete
    绕过实例保护。本周不提供留存清理入口。
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_logs",
        verbose_name="操作者",
        null=True,
        blank=True,
    )
    actor_role = models.CharField("操作时身份", max_length=32, null=True, blank=True)
    actor_is_admin = models.BooleanField("操作时管理员权限", null=True, blank=True)
    action = models.CharField("动作", max_length=32)
    target_type = models.CharField("对象类型", max_length=32)
    target_id = models.BigIntegerField("历史对象主键", null=True, blank=True)
    reason = models.TextField("操作原因", null=True, blank=True)
    created_at = models.DateTimeField("操作时间", db_default=Now())

    class Meta:
        db_table = "audit_log"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    actor__isnull=True,
                    actor_role__isnull=True,
                    actor_is_admin__isnull=True,
                ) | Q(
                    actor__isnull=False,
                    actor_role__isnull=False,
                    actor_is_admin__isnull=False,
                ),
                name="audit_actor_triple_chk",
            ),
        ]
        indexes = [
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
            models.Index(
                fields=["actor", "-created_at"],
                name="audit_actor_created_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        """
        新建审计日志，禁止通过已有实例更新记录。

        Params:
            args: 传递给 Django Model.save 的位置参数
            kwargs: 传递给 Django Model.save 的关键字参数，如 using

        Raises:
            RuntimeError: 实例已经保存过，或请求强制更新
        """
        if (
            not self._state.adding
            or kwargs.get("force_update")
            or kwargs.get("update_fields") is not None
        ):
            raise RuntimeError("审计日志只允许新建")
        # 强制 INSERT，避免新实例显式指定已有主键时退化为 UPDATE。
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        拒绝删除审计日志，保留至少一年的独立审计记录。

        Params:
            args: Django Model.delete 的位置参数
            kwargs: Django Model.delete 的关键字参数

        Raises:
            RuntimeError: 本周不提供审计日志删除入口
        """
        raise RuntimeError("审计日志不允许删除")

    def __str__(self) -> str:
        """返回仅含数据库主键的审计记录标识。"""
        return f"AuditLog({self.pk})"
