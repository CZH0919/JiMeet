"""对方主页与双人聊天的会话认证接口。"""
from apps.chat import selectors, services
from apps.chat.serializers import (
    ChatPageQuerySerializer, ContactQuerySerializer, ConversationSerializer, HistoryQuerySerializer,
    MessageSerializer, OpenConversationSerializer, ReadMessagesSerializer, SendMessageSerializer,
)
from apps.core import clock
from apps.core.pagination import paginate
from apps.core.responses import created, ok, page
from apps.core.views import PrivateAPIView, validate_data
from apps.recruitments.serializers import PublicUserSerializer


def _conversation_data(user, items, moment):
    """一次批量读取本页会话的末条消息，空会话保持 null。"""
    ids = [row.visible_last_id for row in items if row.visible_last_id is not None]
    messages = selectors.visible_messages(moment).in_bulk(ids)
    return ConversationSerializer(items, many=True, context={"user": user, "last_messages": messages}).data


class PeerProfileView(PrivateAPIView):
    query_serializer_class = ContactQuerySerializer

    def get(self, request, uid):
        """读取对方公开资料，不创建会话。

        Args:
            request: 已登录请求，首次联系须携带 recruitment_id 或 application_id。
            uid: 对方的公开用户编号。

        Returns:
            Response: 200，含公开编号、昵称、身份和已有会话编号（可空）。

        Raises:
            NotFound: 联系来源不可见或与对方不匹配。
            ValidationFailed: 联系本人或同时指定两种来源。
        """
        peer, conversation = selectors.contact_from_source(request.user, uid, **self.query)
        return ok({
            **PublicUserSerializer(peer).data,
            "chat": {"can_chat": True, "conversation_id": conversation.pk if conversation else None},
        })


class ConversationListView(PrivateAPIView):
    query_serializer_class = ChatPageQuerySerializer

    def get(self, request):
        """列出本人会话，不产生已读回执。

        Args:
            request: 已登录请求，可提供 page 和 page_size。

        Returns:
            Response: 200，含对方、最近可见消息和本人未读数的分页会话。

        Raises:
            ValidationFailed: 分页参数无效。
        """
        moment = clock.now()
        items, number, size, total = paginate(selectors.conversation_summaries(request.user, moment), request)
        return page(_conversation_data(request.user, items, moment), number, size, total)

    def post(self, request):
        """创建或复用双方唯一的会话。

        Args:
            request: JSON 含 peer_uid，首次联系须另传招聘或申请编号。

        Returns:
            Response: 首次 201，复用 200，均返回 Conversation。

        Raises:
            NotFound: 目标或首次联系来源不可用。
            ValidationFailed: 目标是本人或来源互斥。
        """
        fields = validate_data(OpenConversationSerializer, request.data)
        conversation, is_new = services.open_conversation(request.user, **fields)
        moment = clock.now()
        row = selectors.conversation_summaries(request.user, moment).get(pk=conversation.pk)
        return ok(_conversation_data(request.user, [row], moment)[0], status=201 if is_new else 200)


class ChatUnreadCountView(PrivateAPIView):
    def get(self, request):
        """返回本人的跨会话未读消息总数，与站内业务通知分别计数。"""
        return ok({"unread_count": selectors.unread_total(request.user, clock.now())})


class MessageListView(PrivateAPIView):
    query_serializer_class = HistoryQuerySerializer

    def get(self, request, conversation_id):
        """按发送时间和编号倒序读取仍在保留期内的消息。

        Args:
            request: 已登录请求，可含 page、page_size 及定位更早消息的 before_id。
            conversation_id: 本人参与的会话编号。

        Returns:
            Response: 200，分页 Message，读取不修改已读时间。

        Raises:
            NotFound: 会话不可见或分页起点不属于本会话的可见历史。
            ValidationFailed: 分页参数无效。
        """
        conversation = selectors.get_conversation(request.user, conversation_id)
        queryset = selectors.message_history(conversation, clock.now(), before_id=self.query.get("before_id"))
        items, number, size, total = paginate(queryset, request)
        return page(MessageSerializer(items, many=True, context={"conversation": conversation}).data, number, size, total)

    def post(self, request, conversation_id):
        """以登录用户为发送者向另一位参与者发送消息。

        Args:
            request: JSON 仅含 content，为 1～500 个 Unicode 码点的纯文本。
            conversation_id: 本人参与的会话编号。

        Returns:
            Response: 201，含服务器分配的消息编号、发送时间及收发双方公开编号。

        Raises:
            NotFound: 会话不可见或对方账号不可用。
            ValidationFailed: 正文不符合消息规则。
            BizError: 超过发送额度时返回 429 和剩余等待秒数。
        """
        fields = validate_data(SendMessageSerializer, request.data)
        message, conversation = services.send_message(request.user, conversation_id, **fields)
        return created(MessageSerializer(message, context={"conversation": conversation}).data)


class ReadMessagesView(PrivateAPIView):
    def post(self, request, conversation_id):
        """确认实际展示给本人的对方消息。

        Args:
            request: JSON 含 message_ids，由 1～50 个不同的对方消息编号组成。
            conversation_id: 本人参与的会话编号。

        Returns:
            Response: 200，updated_count 为本次从未读变为已读的条数。

        Raises:
            NotFound: 会话或任一指定消息不可用，整批不写入。
        """
        fields = validate_data(ReadMessagesSerializer, request.data)
        count = services.mark_messages_read(request.user, conversation_id, **fields)
        return ok({"updated_count": count})
