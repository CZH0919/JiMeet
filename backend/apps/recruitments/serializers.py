"""招募输入校验与输出字段白名单；数据库查询由 selectors/services 负责。"""

from django.conf import settings
from rest_framework import serializers

from apps.core.choices import RecruitmentStatus, RecruitmentType, Role
from apps.core.serializers import (
    AwareDateTimeField,
    QueryIntegerField,
    StrictCharField,
    StrictIntegerField,
    StrictQuerySerializer,
    StrictSerializer,
)
from apps.recruitments.models import Recruitment

MAX_RESOURCE_ID = 2**63 - 1


class RecruitmentWriteSerializer(StrictSerializer):
    """POST 必填业务字段；PATCH 只接受提供的可写字段，禁止空修改。"""

    title = StrictCharField(max_length=100)
    type = serializers.ChoiceField(choices=RecruitmentType.choices)
    description = StrictCharField()
    tag_ids = serializers.ListField(
        child=StrictIntegerField(min_value=1, max_value=MAX_RESOURCE_ID), allow_empty=False,
    )
    min_headcount = StrictIntegerField(min_value=1, allow_null=True, required=False, default=None)
    max_headcount = StrictIntegerField(min_value=1, max_value=settings.MAX_HEADCOUNT_LIMIT)
    deadline = AwareDateTimeField()

    def validate_tag_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("标签不能重复")
        return value

    def validate(self, attrs):
        if self.partial and not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs


class RecruitmentDeleteSerializer(StrictSerializer):
    """管理员删除原因在写服务中按操作者身份检查必填。"""

    reason = StrictCharField(required=False, max_length=500)


class RecruitmentQuerySerializer(StrictQuerySerializer):
    """列表过滤；页码语义继续由公共分页工具统一处理。"""

    q = serializers.CharField(required=False, allow_blank=True, default="")
    type = serializers.ChoiceField(choices=RecruitmentType.choices, required=False)
    status = serializers.ChoiceField(choices=RecruitmentStatus.choices, required=False)
    tag = QueryIntegerField(min_value=1, max_value=MAX_RESOURCE_ID, required=False)
    page = serializers.CharField(required=False, allow_blank=True)
    page_size = serializers.CharField(required=False, allow_blank=True)


class PublicUserSerializer(serializers.Serializer):
    """招募中只嵌入公开身份，不暴露姓名、邮箱或数据库用户主键。"""

    uid = serializers.CharField(read_only=True)
    nickname = serializers.CharField(read_only=True)
    role = serializers.ChoiceField(choices=Role.choices, read_only=True)


class TagSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class RecruitmentSummarySerializer(serializers.ModelSerializer):
    """仅序列化已计算有效状态的只读招募快照。"""

    publisher = PublicUserSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    is_deleted = serializers.SerializerMethodField()

    class Meta:
        model = Recruitment
        fields = (
            "id", "title", "type", "tags", "min_headcount", "max_headcount",
            "accepted_count", "status", "is_deleted", "deadline", "publisher",
            "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_is_deleted(self, instance):
        return instance.deleted_at is not None


class RecruitmentDetailSerializer(RecruitmentSummarySerializer):
    """私有详情来自已鉴权的查询上下文，非发布者不返回申请计数。"""

    my_application = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    application_counts = serializers.SerializerMethodField()

    class Meta(RecruitmentSummarySerializer.Meta):
        fields = RecruitmentSummarySerializer.Meta.fields + (
            "description", "closed_at", "full_at", "close_reason",
            "my_application", "permissions", "application_counts",
        )
        read_only_fields = fields

    def get_my_application(self, instance):
        return self.context["my_application"]

    def get_permissions(self, instance):
        return self.context["permissions"]

    def get_application_counts(self, instance):
        return self.context.get("application_counts")

    def to_representation(self, instance):
        result = super().to_representation(instance)
        if "application_counts" not in self.context:
            result.pop("application_counts")
        return result
