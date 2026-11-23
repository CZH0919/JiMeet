"""站内联系来源、消息输入与对外字段。"""
from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.chat import selectors
from apps.chat.models import ChatMessage
from apps.chat.services import MAX_CONTENT_LENGTH, MAX_READ_RECEIPTS
from apps.core.serializers import (
    QueryIntegerField, StrictCharField, StrictIntegerField, StrictQuerySerializer, StrictSerializer,
)
from apps.recruitments.serializers import MAX_RESOURCE_ID, PublicUserSerializer


class ContactQuerySerializer(StrictQuerySerializer):
    recruitment_id = QueryIntegerField(min_value=1, max_value=MAX_RESOURCE_ID, required=False)
    application_id = QueryIntegerField(min_value=1, max_value=MAX_RESOURCE_ID, required=False)


class OpenConversationSerializer(StrictSerializer):
    peer_uid = StrictCharField(
        trim_whitespace=False, min_length=32, max_length=32,
        validators=[RegexValidator(r"\A[0-9a-f]{32}\Z", "须为 32 位小写十六进制公开编号")],
    )
    recruitment_id = StrictIntegerField(min_value=1, max_value=MAX_RESOURCE_ID, required=False)
    application_id = StrictIntegerField(min_value=1, max_value=MAX_RESOURCE_ID, required=False)


class ChatPageQuerySerializer(StrictQuerySerializer):
    page = serializers.CharField(required=False, allow_blank=True)
    page_size = serializers.CharField(required=False, allow_blank=True)


class HistoryQuerySerializer(ChatPageQuerySerializer):
    before_id = QueryIntegerField(min_value=1, max_value=MAX_RESOURCE_ID, required=False)


class SendMessageSerializer(StrictSerializer):
    content = StrictCharField(max_length=MAX_CONTENT_LENGTH, trim_whitespace=False)


class ReadMessagesSerializer(StrictSerializer):
    message_ids = serializers.ListField(
        child=StrictIntegerField(min_value=1, max_value=MAX_RESOURCE_ID),
        allow_empty=False, max_length=MAX_READ_RECEIPTS,
    )

    def validate_message_ids(self, ids):
        """一个回执中每条消息只列一次。"""
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("消息编号不能重复")
        return ids


class MessageSerializer(serializers.ModelSerializer):
    """发送者与接收者均用公开编号表示。调用方提供已鉴权的会话。"""

    sender_uid = serializers.SerializerMethodField()
    recipient_uid = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ("id", "conversation_id", "sender_uid", "recipient_uid", "content", "created_at", "read_at")
        read_only_fields = fields

    def get_sender_uid(self, message):
        conversation = self.context["conversation"]
        return (conversation.user_low if message.sender_id == conversation.user_low_id else conversation.user_high).uid

    def get_recipient_uid(self, message):
        conversation = self.context["conversation"]
        return (conversation.user_high if message.sender_id == conversation.user_low_id else conversation.user_low).uid


class ConversationSerializer(serializers.Serializer):
    """对参与者展示对方、当前可见的最近一条消息及本人未读数。"""

    id = serializers.IntegerField(read_only=True)
    peer = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()

    def get_peer(self, conversation):
        peer = selectors.peer_of(conversation, self.context["user"])
        return PublicUserSerializer(peer).data

    def get_last_message(self, conversation):
        message = self.context["last_messages"].get(conversation.visible_last_id)
        if message is None:
            return None
        return MessageSerializer(message, context={"conversation": conversation}).data

    def get_unread_count(self, conversation):
        return conversation.unread or 0

    def get_updated_at(self, conversation):
        moment = conversation.visible_last_at or conversation.created_at
        return serializers.DateTimeField().to_representation(moment)
