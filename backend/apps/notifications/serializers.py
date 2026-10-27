"""通知查询参数和公开响应字段白名单。"""

from rest_framework import serializers

from apps.core.serializers import StrictCharField, StrictQuerySerializer
from apps.notifications.models import Notification


class NotificationQuerySerializer(StrictQuerySerializer):
    is_read = StrictCharField(required=False, trim_whitespace=False)
    page = serializers.CharField(required=False, allow_blank=True)
    page_size = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if "is_read" in attrs:
            value = attrs["is_read"]
            if value not in {"true", "false"}:
                raise serializers.ValidationError({"is_read": "只能是 true 或 false"})
            attrs["is_read"] = value == "true"
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    recruitment_id = serializers.IntegerField(read_only=True, allow_null=True)
    application_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Notification
        fields = (
            "id", "type", "title", "content", "recruitment_id",
            "application_id", "is_read", "created_at",
        )
        read_only_fields = fields
