"""申请输入白名单及按业务关系裁剪的输出；不查询数据库或生成文件 URL。"""

from rest_framework import serializers

from apps.applications import policies
from apps.applications.models import Application
from apps.core.choices import ApplicationStatus
from apps.core.serializers import (
    AwareDateTimeField, QueryIntegerField, StrictCharField, StrictQuerySerializer, StrictSerializer,
)
from apps.recruitments.serializers import PublicUserSerializer


class ApplicationUpdateSerializer(StrictSerializer):
    """申请修改输入：至少提供 note 或 resume，空说明表示清空。"""
    note = StrictCharField(required=False, allow_blank=True)
    resume = serializers.FileField(required=False, allow_empty_file=True)

    def to_internal_value(self, data):
        """校验 multipart 字段白名单及单值约束。

        Args:
            data: 包含文本与上传文件的映射或 QueryDict。

        Returns:
            dict: 通过字段校验的输入。

        Raises:
            ValidationError: 字段重复、未知，或不符合各字段要求。
        """
        if hasattr(data, "getlist"):
            repeated = {key: "字段不能重复" for key in data if len(data.getlist(key)) != 1}
            if repeated:
                raise serializers.ValidationError(repeated)
            data = dict(data.items())
        return super().to_internal_value(data)

    def validate_note(self, value):
        """将空说明规范化为 None。

        Args:
            value: 已去除首尾空白的字符串或 None。

        Returns:
            str | None: 非空说明原样返回，空值转换为 None。
        """
        return value or None

    def validate(self, attrs):
        """要求修改请求至少包含一个可写字段。

        Args:
            attrs: 已校验的 note/resume 字段映射。

        Returns:
            dict: 原已校验映射。

        Raises:
            ValidationError: 请求为空。
        """
        if not attrs:
            raise serializers.ValidationError("至少提供 note 或 resume")
        return attrs


class ApplicationActionSerializer(StrictSerializer):
    """JSON 动作输入：仅 read 接受并要求 seen_updated_at。"""
    seen_updated_at = AwareDateTimeField(required=False)

    def validate(self, attrs):
        """按 context.action 校验已阅版本字段。

        Args:
            attrs: 已完成字段级校验的输入。

        Returns:
            dict: 合法的动作参数。

        Raises:
            ValidationError: read 缺少 seen_updated_at，或其他动作提交了该字段。
        """
        action = self.context["action"]
        if action == "read" and "seen_updated_at" not in attrs:
            raise serializers.ValidationError({"seen_updated_at": "此字段为必填项"})
        if action != "read" and "seen_updated_at" in attrs:
            raise serializers.ValidationError({"seen_updated_at": "仅 read 操作接受此字段"})
        return attrs


class ApplicationSubmitSerializer(StrictSerializer):
    """投递输入：单个简历文件及可选说明，拒绝未知和重复字段。"""
    resume = serializers.FileField(allow_empty_file=True)
    note = StrictCharField(required=False, allow_blank=True, default=None)

    def to_internal_value(self, data):
        """校验 multipart 字段白名单及单值约束。

        Args:
            data: 包含文本与上传文件的映射或 QueryDict。

        Returns:
            dict: 通过字段校验的输入。

        Raises:
            ValidationError: 字段重复、未知，或不符合各字段要求。
        """
        if hasattr(data, "getlist"):
            repeated = {key: "字段不能重复" for key in data if len(data.getlist(key)) != 1}
            if repeated:
                raise serializers.ValidationError(repeated)
            # 保留空 note，并拒绝文本/文件同名及多个 resume 文件。
            data = dict(data.items())
        return super().to_internal_value(data)

    def validate_note(self, value):
        """将空说明规范化为 None。

        Args:
            value: 已去除首尾空白的字符串或 None。

        Returns:
            str | None: 非空说明原样返回，空值转换为 None。
        """
        return value or None


class ApplicationQuerySerializer(StrictQuerySerializer):
    status = serializers.ChoiceField(choices=ApplicationStatus.choices, required=False)
    page = serializers.CharField(required=False, allow_blank=True)
    page_size = serializers.CharField(required=False, allow_blank=True)


class MyApplicationQuerySerializer(ApplicationQuerySerializer):
    recruitment_id = QueryIntegerField(min_value=1, max_value=2**63 - 1, required=False)


class RecruitmentReferenceSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    is_deleted = serializers.SerializerMethodField()
    deleted_at = serializers.DateTimeField(read_only=True, allow_null=True)

    def get_is_deleted(self, instance):
        """生成历史引用中的招募删除标记。

        Args:
            instance: 招募对象。

        Returns:
            bool: deleted_at 是否非空。
        """
        return instance.deleted_at is not None


class ApplicationSummarySerializer(serializers.ModelSerializer):
    """只接受已鉴权和投影的快照，公共字段采用显式白名单。"""

    recruitment = RecruitmentReferenceSerializer(read_only=True)
    applicant = PublicUserSerializer(read_only=True)

    class Meta:
        model = Application
        fields = ("id", "recruitment", "applicant", "status", "created_at", "updated_at", "decided_at")
        read_only_fields = fields

    def to_representation(self, instance):
        """按当前业务关系输出申请字段。

        Args:
            instance: 已鉴权并完成时间投影的申请；context 必须包含 user 和 now。

        Returns:
            dict: 摘要不返回申请说明或简历元数据；发布者按权限获得姓名和私有标记。

        Raises:
            ValueError: 申请对象对当前用户不可见。
        """
        user, now = self.context["user"], self.context["now"]
        access = policies.resolve_application_access(user, instance, instance.recruitment, now)
        if not access.can_view:
            raise ValueError("不能序列化未授权的申请")
        result = super().to_representation(instance)
        if access.can_see_applicant_name:
            result["applicant"]["name"] = instance.applicant.name
        if access.can_see_publisher_mark:
            result["publisher_mark"] = instance.publisher_mark
            result["has_unseen_update"] = instance.has_unseen_update
        result["permissions"] = {
            "can_modify": policies.can_modify_application(user, instance, instance.recruitment),
            "can_withdraw": policies.can_withdraw_application(user, instance, instance.recruitment),
            "can_process": policies.can_process_application(user, instance, instance.recruitment, now),
            "can_download_resume": access.can_download_resume,
        }
        return result


class ApplicationDetailSerializer(ApplicationSummarySerializer):
    """在申请摘要上按权限补充说明及简历元数据，不暴露存储路径。"""
    def to_representation(self, instance):
        """按当前业务关系输出申请字段。

        Args:
            instance: 已鉴权并完成时间投影的申请；context 必须包含 user 和 now。

        Returns:
            dict: 在摘要上仅向有权限的用户输出 note 和 resume 元数据。

        Raises:
            ValueError: 申请对象对当前用户不可见。
        """
        result = super().to_representation(instance)
        access = policies.resolve_application_access(
            self.context["user"], instance, instance.recruitment, self.context["now"],
        )
        if access.can_see_note:
            result["note"] = instance.note
        if access.can_download_resume:
            result["resume"] = {
                "name": instance.resume_name, "size": instance.resume_size, "type": instance.resume_type,
            }
        return result
