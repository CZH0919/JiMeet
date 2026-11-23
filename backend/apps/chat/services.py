"""会话建立、发送限流、已读回执及到期消息清理。"""
from datetime import timedelta
import logging
from math import ceil
import re
from unicodedata import category

from django.db import DatabaseError, transaction
from django.db.models import OuterRef, Q, Subquery

from apps.accounts.models import User
from apps.chat import selectors
from apps.chat.models import ChatConversation, ChatMessage, ChatSendPause
from apps.core import clock
from apps.core.errors import BizError, ErrorCode, NotFound, ValidationFailed


logger = logging.getLogger(__name__)
SEND_WINDOW = timedelta(minutes=1)
SEND_LIMIT = 50
MAX_CONTENT_LENGTH = 500
MAX_READ_RECEIPTS = 50
HTML_MARKUP = re.compile(r"</?[a-z][\w:-]*(?:\s[^<>]*)?\s*/?>|<!--|<!doctype\b|<\?", re.IGNORECASE)


def open_conversation(user, *, peer_uid, recruitment_id=None, application_id=None):
    """从合法来源建立双人会话，重复或相向并发发起均复用同一条记录。

    Args:
        user: 已登录的发起人。
        peer_uid: 对方公开编号。
        recruitment_id: 可选的公开招聘入口编号。
        application_id: 可选的本人收到的申请编号，与招聘入口互斥。

    Returns:
        (ChatConversation, bool): 会话以及是否由本次请求首次创建。

    Raises:
        NotFound: 首次联系缺少合法来源或目标账号不可用。
        ValidationFailed: 目标为本人或同时指定两种来源。
    """
    with transaction.atomic():
        participants = User.objects.select_for_update(no_key=True).filter(
            Q(pk=user.pk) | Q(uid=peer_uid), is_active=True,
        ).order_by("pk")
        if user.pk not in list(participants.values_list("pk", flat=True)):
            raise NotFound("联系入口不可用")
        peer, existing = selectors.contact_from_source(
            user, peer_uid, recruitment_id=recruitment_id, application_id=application_id, lock_source=True,
        )
        if existing is not None:
            return existing, False
        low, high = sorted((user.pk, peer.pk))
        return ChatConversation.objects.get_or_create(user_low_id=low, user_high_id=high)


def _validate_content(content) -> None:
    """校验 1～500 个 Unicode 码点的纯文本，保留正常换行及 Emoji 组合。"""
    if not isinstance(content, str) or not 1 <= len(content) <= MAX_CONTENT_LENGTH:
        raise ValidationFailed(details={"content": "消息须为 1 至 500 个字符的纯文本"})
    if any(category(c) in {"Cc", "Cs"} and c not in "\n\r\t" for c in content):
        raise ValidationFailed(details={"content": "消息含有无效控制字符"})
    if not any(not c.isspace() and category(c) not in {"Cf", "Mn", "Me"} for c in content):
        raise ValidationFailed(details={"content": "消息不能为空"})
    if HTML_MARKUP.search(content):
        raise ValidationFailed(details={"content": "请以纯文本发送消息"})


def _pause_remaining(user, moment):
    """调用方已锁定发送者账号。返回剩余暂停秒数，首个超额请求固定暂停一分钟。"""
    pause = ChatSendPause.objects.filter(user=user).first()
    if pause is not None and pause.blocked_until > moment:
        return ceil((pause.blocked_until - moment).total_seconds())
    recent = ChatMessage.objects.filter(sender=user, created_at__gt=moment - SEND_WINDOW, created_at__lte=moment)
    if recent.count() < SEND_LIMIT:
        return 0
    ChatSendPause.objects.update_or_create(user=user, defaults={"blocked_until": moment + SEND_WINDOW})
    return int(SEND_WINDOW.total_seconds())


def send_message(user, conversation_id, *, content):
    """在本人会话中发送消息，正文、会话活动时间和发送额度在同一事务内确定。

    Args:
        user: 已登录的发送者。
        conversation_id: 发送者参与的会话编号。
        content: 保留原空格和换行的纯文本。

    Returns:
        (ChatMessage, ChatConversation): 已保存的消息和已加载参与者的会话。

    Raises:
        NotFound: 会话不可见或参与账号不可用。
        ValidationFailed: 正文不符合纯文本或长度要求。
        BizError: 发送超限返回 429 和剩余暂停秒数，数据库写入失败返回 500。
    """
    with transaction.atomic():
        active = User.objects.select_for_update(no_key=True).filter(pk=user.pk, is_active=True)
        if active.values_list("pk", flat=True).first() is None:
            raise NotFound("联系入口不可用")
        conversation = selectors.get_conversation(user, conversation_id, lock=True)
        _validate_content(content)
        if not User.objects.filter(pk=selectors.peer_of(conversation, user).pk, is_active=True).exists():
            raise NotFound("联系入口不可用")
        moment = clock.now()
        remaining = _pause_remaining(user, moment)
        if not remaining:
            try:
                message = ChatMessage.objects.create(
                    conversation=conversation, sender=user, content=content, created_at=moment,
                )
            except DatabaseError as error:
                # 数据库错误详情可能包含待写入的正文，只保留可定位的元数据。
                logger.error("chat_message_write_failed conversation_id=%s error=%s", conversation.pk, type(error).__name__)
                raise BizError("消息保存失败，请稍后重试") from None
            if conversation.last_message_at is None or moment > conversation.last_message_at:
                conversation.last_message_at = moment
                conversation.save(update_fields=["last_message_at"])
            transaction.on_commit(lambda: logger.info(
                "chat_message_sent conversation_id=%s message_id=%s", conversation.pk, message.pk,
            ))
    # 暂停状态须先提交，随后返回本次限流结果。
    if remaining:
        raise BizError("发送过于频繁，请稍后重试", code=ErrorCode.RATE_LIMITED, http_status=429,
                       details={"retry_after": remaining})
    return message, conversation


def mark_messages_read(user, conversation_id, *, message_ids):
    """仅标记该用户实际展示的对方消息，返回此次从未读变为已读的条数。

    已读回执可重复提交。任一编号不可见则整批返回 404，保留原状态。
    """
    with transaction.atomic():
        conversation = selectors.get_conversation(user, conversation_id, lock=True)
        moment = clock.now()
        incoming = ChatMessage.objects.filter(
            conversation=conversation, sender=selectors.peer_of(conversation, user),
            expires_at__gt=moment, pk__in=message_ids,
        )
        if incoming.count() != len(message_ids):
            raise NotFound("回执包含不可用的消息")
        return incoming.filter(read_at__isnull=True).update(read_at=moment)


def purge_expired_messages(*, batch_size=500, moment=None):
    """按批物理删除达到六个月期限的消息，保留会话并校正最近消息时间。

    Args:
        batch_size: 单批处理的消息数，须为正整数。
        moment: 本轮统一到期判断时刻，默认使用业务时钟。

    Returns:
        int: 实际删除的消息条数。重复执行不重复计数。
    """
    if batch_size < 1:
        raise ValueError("批大小须为正整数")
    moment = moment or clock.now()
    expired = ChatMessage.objects.filter(expires_at__lte=moment)
    deleted = 0
    while candidates := list(expired.order_by("expires_at", "pk").values_list("pk", "conversation_id")[:batch_size]):
        ids, conversation_ids = zip(*candidates)
        with transaction.atomic():
            conversations = ChatConversation.objects.filter(pk__in=set(conversation_ids))
            # 先按主键顺序锁定会话，与发送及已读使用相同的会话锁。
            list(conversations.order_by("pk").select_for_update(no_key=True).values_list("pk", flat=True))
            removed, _ = expired.filter(pk__in=ids).delete()
            if removed:
                latest = selectors.visible_messages(moment).filter(
                    conversation_id=OuterRef("pk"),
                ).order_by("-created_at", "-pk").values("created_at")[:1]
                conversations.update(last_message_at=Subquery(latest))
                deleted += removed
    return deleted
