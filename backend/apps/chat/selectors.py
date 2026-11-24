"""对方主页、会话及仍在保留期内的消息查询。"""

from django.db.models import Count, F, OuterRef, Q, Subquery

from apps.accounts.models import User
from apps.applications.models import Application
from apps.chat.models import ChatConversation, ChatMessage
from apps.core import clock
from apps.recruitments.lifecycle import expired_recruitments
from apps.core.errors import NotFound, ValidationFailed
from apps.recruitments.models import Recruitment


def conversations_for(user):
    """只返回当前用户参与的会话，并预加载双方的公开资料。"""
    return (
        ChatConversation.objects.filter(Q(user_low=user) | Q(user_high=user))
        .select_related("user_low", "user_high")
        .only("created_at", "last_message_at",
              "user_low__uid", "user_low__nickname", "user_low__role", "user_low__is_active", "user_low__cancelled_at",
              "user_high__uid", "user_high__nickname", "user_high__role", "user_high__is_active", "user_high__cancelled_at")
    )


def get_conversation(user, conversation_id, *, lock=False):
    """按参与关系定位会话。写操作可在事务内锁定会话，不可见时返回 404。"""
    queryset = conversations_for(user)
    if lock:
        queryset = queryset.select_for_update(of=("self",), no_key=True)
    try:
        return queryset.get(pk=conversation_id)
    except ChatConversation.DoesNotExist:
        raise NotFound("会话不存在") from None


def peer_of(conversation, user):
    """返回当前参与者对应的另一方，用于已完成成员校验的会话。"""
    return conversation.user_high if user.pk == conversation.user_low_id else conversation.user_low


def contact_from_source(user, uid, *, recruitment_id=None, application_id=None, lock_source=False):
    """读取可联系的对方及已有会话；首次联系校验招聘发布者或本人收到的申请。

    Args:
        user: 已登录的发起人。
        uid: 对方的公开编号。
        recruitment_id: 公开招聘入口，对方必须是发布者。
        application_id: 收到的申请入口，本人必须是发布者且对方是该申请人。
        lock_source: 建会话时在业务事务内锁定来源，避免与删除来源交错。

    Returns:
        (User, ChatConversation | None): 对方与已有会话；查询不会创建会话。

    Raises:
        ValidationFailed: 联系本人或同时传入两种来源。
        NotFound: 对方不可用、来源不匹配，或首次联系没有合法来源。
    """
    if recruitment_id is not None and application_id is not None:
        raise ValidationFailed(details={"source": "只可提供一种联系来源"})
    if uid == user.uid:
        raise ValidationFailed(details={"peer_uid": "不能与自己发起会话"})
    peer = User.objects.filter(uid=uid, is_active=True).only("uid", "nickname", "role", "cancelled_at").first()
    if peer is None:
        raise NotFound("联系入口不可用")
    low, high = sorted((user.pk, peer.pk))
    existing = ChatConversation.objects.filter(user_low_id=low, user_high_id=high).first()
    if existing is not None:
        return peer, existing
    if recruitment_id is not None:
        source = Recruitment.objects.filter(pk=recruitment_id, publisher=peer, deleted_at__isnull=True)
    elif application_id is not None:
        source = Application.objects.filter(pk=application_id, applicant=peer, recruitment__publisher=user).exclude(
            expired_recruitments(clock.now(), "recruitment__"),
        )
    else:
        raise NotFound("联系入口不可用")
    if lock_source:
        source = source.select_for_update(of=("self",), no_key=True)
    if source.values_list("pk", flat=True).first() is None:
        raise NotFound("联系入口不可用")
    return peer, None


def visible_messages(moment):
    """查询发送者属于会话且在给定时刻尚未到期的消息。"""
    return ChatMessage.objects.filter(
        Q(sender_id=F("conversation__user_low_id")) | Q(sender_id=F("conversation__user_high_id")),
        expires_at__gt=moment,
    )


def conversation_summaries(user, moment):
    """为本人的会话标注可见末条消息及未读数；未发过或全部过期的会话排在最后。"""
    latest = visible_messages(moment).filter(conversation_id=OuterRef("pk")).order_by("-created_at", "-pk")
    incoming = visible_messages(moment).filter(
        conversation_id=OuterRef("pk"), read_at__isnull=True,
    ).exclude(sender=user).order_by().values("conversation_id").annotate(total=Count("pk"))
    return conversations_for(user).annotate(
        visible_last_id=Subquery(latest.values("pk")[:1]),
        visible_last_at=Subquery(latest.values("created_at")[:1]),
        unread=Subquery(incoming.values("total")[:1]),
    ).order_by(F("visible_last_at").desc(nulls_last=True), "-created_at", "-pk")


def unread_total(user, moment):
    """计算所有本人会话中尚未到期、由对方发出的未读消息数。"""
    return visible_messages(moment).filter(
        Q(conversation__user_low=user) | Q(conversation__user_high=user), read_at__isnull=True,
    ).exclude(sender=user).count()


def message_history(conversation, moment, *, before_id=None):
    """按发送时间和编号倒序读取历史；可用同一会话中的可见消息定位更早一页。"""
    messages = visible_messages(moment).filter(conversation=conversation)
    if before_id is not None:
        anchor = messages.filter(pk=before_id).values("created_at").first()
        if anchor is None:
            raise NotFound("分页起点不存在")
        sent_at = anchor["created_at"]
        messages = messages.filter(Q(created_at__lt=sent_at) | Q(created_at=sent_at, pk__lt=before_id))
    return messages.order_by("-created_at", "-pk")
