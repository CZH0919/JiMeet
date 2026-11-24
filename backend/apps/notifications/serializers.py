"""通知查询参数和公开响应字段白名单。"""

from rest_framework import serializers

from apps.core.serializers import StrictCharField, StrictQuerySerializer
from apps.notifications.models import Notification


class NotificationQuerySerializer(StrictQuerySerializer):
    is_read = StrictCharField(required=False, trim_whitespace=False)
    page = serializers.CharField(required=False, allow_blank=True)
    page_size = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        """将严格的小写已读查询值转换为布尔值。

        Args:
            attrs: 已校验的查询字段映射；is_read 可省略。

        Returns:
            dict: 若提供 is_read，则转换为 bool。

        Raises:
            ValidationError: is_read 不是字符串 true 或 false，包括空值和大小写变体。
        """
        if "is_read" in attrs:
            value = attrs["is_read"]
            if value not in {"true", "false"}:
                raise serializers.ValidationError({"is_read": "只能是 true 或 false"})
            attrs["is_read"] = value == "true"
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    recruitment_id = serializers.IntegerField(read_only=True, allow_null=True)
    application_id = serializers.IntegerField(read_only=True, allow_null=True)
    announcement_id = serializers.IntegerField(read_only=True, allow_null=True)
    target_is_deleted = serializers.SerializerMethodField()

    def get_target_is_deleted(self, instance):
        """返回关联招聘或公告当前是否已删除，不改变历史通知内容。

        Args:
            instance: 已经接收人与关联权限过滤的通知，目标由查询层预加载。

        Returns:
            bool: 关联招聘或公告已软删除时为 True；无关联旧通知为 False。
                该标记不表示申请状态，也不授予目标详情或简历访问权。
        """
        target = instance.announcement if instance.announcement_id is not None else instance.recruitment
        return target is not None and target.deleted_at is not None

    class Meta:
        model = Notification
        fields = (
            "id", "type", "title", "content", "recruitment_id",
            "application_id", "announcement_id", "target_is_deleted", "is_read", "created_at",
        )
        read_only_fields = fields
