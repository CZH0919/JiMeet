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
    description = StrictCharField(max_length=5000)
    tag_ids = serializers.ListField(
        child=StrictIntegerField(min_value=1, max_value=MAX_RESOURCE_ID), allow_empty=False,
    )
    min_headcount = StrictIntegerField(min_value=1, allow_null=True, required=False, default=None)
    max_headcount = StrictIntegerField(min_value=1, max_value=settings.MAX_HEADCOUNT_LIMIT)
    deadline = AwareDateTimeField()

    def validate_tag_ids(self, value):
        """拒绝重复标签主键。

        Args:
            value: 已通过整数范围校验的非空 ID 列表。

        Returns:
            list[int]: 原标签列表，启用状态由写服务在事务内校验。

        Raises:
            ValidationError: 标签主键重复。
        """
        if len(value) != len(set(value)):
            raise serializers.ValidationError("标签不能重复")
        return value

    def validate(self, attrs):
        """拒绝不包含可写字段的部分更新。

        Args:
            attrs: 已通过字段级校验的输入映射。

        Returns:
            dict: 原已校验数据。

        Raises:
            ValidationError: partial=True 且输入为空。
        """
        if self.partial and not attrs:
            raise serializers.ValidationError("至少提供一个可修改字段")
        return attrs


class RecruitmentDeleteSerializer(StrictSerializer):
    """本人删除原因可选，管理员身份不改变该入口的权限。"""

    reason = StrictCharField(required=False, max_length=500)


class RecruitmentGovernanceSerializer(StrictSerializer):
    """治理删除必须提供非空原因。"""

    reason = StrictCharField(min_length=1, max_length=500)


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
        """生成招募删除标记。

        Args:
            instance: 已投影的招募对象。

        Returns:
            bool: deleted_at 是否非空。
        """
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
        """读取当前用户的最新申请摘要。

        Args:
            instance: 当前招募对象；实际值来自 detail_context 生成的 serializer.context。

        Returns:
            dict | None: 从查询上下文读取的申请 id/status 或 None。
        """
        return self.context["my_application"]

    def get_permissions(self, instance):
        """读取当前用户的招募操作权限。

        Args:
            instance: 当前招募对象；实际值来自 detail_context 生成的 serializer.context。

        Returns:
            dict: 查询上下文中已计算的权限与投递阻断原因。
        """
        return self.context["permissions"]

    def get_application_counts(self, instance):
        """读取仅向发布者提供的申请状态计数。

        Args:
            instance: 当前招募对象；实际值来自 detail_context 生成的 serializer.context。

        Returns:
            dict | None: 查询上下文中的计数；没有该权限时为 None，最终响应会省略该字段。
        """
        return self.context.get("application_counts")

    def to_representation(self, instance):
        """序列化招募详情并省略无权限的申请计数。

        Args:
            instance: 已完成时间投影的招募，context 必须由 detail_context 构造。

        Returns:
            dict: 招募详情；非发布者没有 application_counts 字段。
        """
        result = super().to_representation(instance)
        if "application_counts" not in self.context:
            result.pop("application_counts")
        return result
