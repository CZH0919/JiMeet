from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now


class ChatConversation(models.Model):
    """
    两人会话模型，对应 database.md 1.7 的 chat_conversation 表。

    ### Attributes
    - `user_low` / `user_high`: 按用户主键从小到大保存的两名参与者
    - `last_message_at`: 可空的最近消息时间，供会话列表排序
    - `created_at`: 会话创建时间

    数据库保证 user_low < user_high，且每对用户只存在一个会话。
    会话独立于招聘与申请，不注册到 Django Admin。
    """

    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chat_conversations_low",
        verbose_name="较小主键参与者",
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chat_conversations_high",
        verbose_name="较大主键参与者",
    )
    last_message_at = models.DateTimeField("最近消息时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", db_default=Now())

    class Meta:
        db_table = "chat_conversation"
        constraints = [
            models.CheckConstraint(
                condition=Q(user_low__lt=F("user_high")),
                name="chat_conversation_order_chk",
            ),
            models.UniqueConstraint(
                fields=["user_low", "user_high"],
                name="chat_conversation_users_uniq",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的会话标识。"""
        return f"ChatConversation({self.pk})"


class ChatMessage(models.Model):
    """
    纯文本聊天消息模型，对应 database.md 1.7 的 chat_message 表。

    ### Attributes
    - `conversation`: 所属两人会话
    - `sender`: 发送者，必须是会话参与者，由应用层校验
    - `content`: 消息正文，1～2000 字符由应用层校验
    - `created_at` / `read_at`: 发送时间与可空的对方已读时间

    本模型不注册到 Django Admin，管理员权限不授予聊天内容访问权。
    """

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.PROTECT,
        related_name="messages",
        verbose_name="会话",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chat_messages",
        verbose_name="发送者",
    )
    content = models.TextField("消息内容")
    created_at = models.DateTimeField("发送时间", db_default=Now())
    read_at = models.DateTimeField("已读时间", null=True, blank=True)

    class Meta:
        db_table = "chat_message"
        indexes = [
            models.Index(
                fields=["conversation", "created_at"],
                name="chat_message_conversation_idx",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的消息标识，避免输出正文。"""
        return f"ChatMessage({self.pk})"
