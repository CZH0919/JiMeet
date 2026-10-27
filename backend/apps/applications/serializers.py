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
    note = StrictCharField(required=False, allow_blank=True)
    resume = serializers.FileField(required=False, allow_empty_file=True)

    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            repeated = {key: "字段不能重复" for key in data if len(data.getlist(key)) != 1}
            if repeated:
                raise serializers.ValidationError(repeated)
            data = dict(data.items())
        return super().to_internal_value(data)

    def validate_note(self, value):
        return value or None

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("至少提供 note 或 resume")
        return attrs


class ApplicationActionSerializer(StrictSerializer):
    seen_updated_at = AwareDateTimeField(required=False)

    def validate(self, attrs):
        action = self.context["action"]
        if action == "read" and "seen_updated_at" not in attrs:
            raise serializers.ValidationError({"seen_updated_at": "此字段为必填项"})
        if action != "read" and "seen_updated_at" in attrs:
            raise serializers.ValidationError({"seen_updated_at": "仅 read 操作接受此字段"})
        return attrs


class ApplicationSubmitSerializer(StrictSerializer):
    resume = serializers.FileField(allow_empty_file=True)
    note = StrictCharField(required=False, allow_blank=True, default=None)

    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            repeated = {key: "字段不能重复" for key in data if len(data.getlist(key)) != 1}
            if repeated:
                raise serializers.ValidationError(repeated)
            # 保留空 note，并拒绝文本/文件同名及多个 resume 文件。
            data = dict(data.items())
        return super().to_internal_value(data)

    def validate_note(self, value):
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
    def to_representation(self, instance):
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
