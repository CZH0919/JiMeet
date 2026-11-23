"""公告请求校验与响应序列化；字段约束见 backend/design_file/api.md 第 8 章。"""
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from rest_framework import serializers

from apps.core.choices import AnnouncementTimeKind
from apps.core.serializers import (
    AwareDateTimeField,
    StrictCharField,
    StrictIntegerField,
    StrictQuerySerializer,
    StrictSerializer,
)
from apps.announcements.models import Announcement, AnnouncementSubmission


def _validate_link_url(value):
    """校验相关链接为 HTTP/HTTPS 绝对地址。

    Args:
        value: 已通过字段校验的字符串或 None。

    Returns:
        str | None: 去首尾空白后的链接；None 原样返回。

    Raises:
        serializers.ValidationError: 非绝对 HTTP/HTTPS 地址。
    """
    if value is None:
        return None
    value = value.strip()
    try:
        URLValidator(schemes=["http", "https"])(value)
        parsed = urlsplit(value)
        if not parsed.hostname:
            raise ValueError("缺少主机名")
        # URLValidator 校验地址结构，port 属性额外校验端口范围。
        _ = parsed.port
    except (DjangoValidationError, ValueError):
        raise serializers.ValidationError("须为合法的 http:// 或 https:// 绝对地址") from None
    return value


class AnnouncementCreateSerializer(StrictSerializer):
    """发布公告的必填与可选字段。"""

    title = StrictCharField(min_length=1, max_length=100)
    content = StrictCharField(min_length=1, max_length=5000)
    time_kind = serializers.ChoiceField(choices=AnnouncementTimeKind.values)
    event_at = AwareDateTimeField()
    link_url = StrictCharField(max_length=500, required=False, allow_null=True)
    recruitment_id = StrictIntegerField(required=False, allow_null=True, min_value=1)

    def validate_link_url(self, value):
        """校验相关链接格式。"""
        return _validate_link_url(value)


class SubmissionCreateSerializer(StrictSerializer):
    """公告投稿内容；提交后不可改稿、撤回。"""

    title = StrictCharField(min_length=1, max_length=100)
    content = StrictCharField(min_length=1, max_length=5000)
    time_kind = serializers.ChoiceField(choices=AnnouncementTimeKind.values)
    event_at = AwareDateTimeField()
    link_url = StrictCharField(max_length=500, required=False, allow_null=True)

    def validate_link_url(self, value):
        """校验相关链接格式。"""
        return _validate_link_url(value)


class SubmissionRejectSerializer(StrictSerializer):
    """驳回投稿的必填理由。"""

    reason = StrictCharField(min_length=1, max_length=500)


class GovernanceDeleteSerializer(StrictSerializer):
    """治理删除的必填原因。"""

    reason = StrictCharField(min_length=1, max_length=500)


class AnnouncementQuerySerializer(StrictQuerySerializer):
    """列表分页查询参数。"""

    page = serializers.CharField(required=False, allow_blank=True)
    page_size = serializers.CharField(required=False, allow_blank=True)


class AnnouncementSerializer(serializers.ModelSerializer):
    """公告输出对象，含作者摘要、关联招募可用性与当前用户权限。"""

    author = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    recruitment_id = serializers.IntegerField(read_only=True, allow_null=True)
    recruitment_available = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = (
            "id", "title", "content", "time_kind", "event_at", "link_url",
            "recruitment_id", "recruitment_available", "is_pinned",
            "created_at", "updated_at", "author", "permissions",
        )
        read_only_fields = fields

    def get_author(self, announcement) -> dict:
        """输出发布者公开信息，不暴露内部标识。

        Args:
            announcement: 公告实例（须预加载 author）。

        Returns:
            dict: uid、nickname、role。
        """
        return {
            "uid": announcement.author.uid,
            "nickname": announcement.author.nickname,
            "role": announcement.author.role,
        }

    def get_recruitment_available(self, announcement) -> bool:
        """关联招募当前是否可用；未关联或已删除为 False。

        Args:
            announcement: 公告实例（须预加载 recruitment）。

        Returns:
            bool: 关联招募存在且未删除时为 True。
        """
        recruitment = announcement.recruitment
        return (
            announcement.recruitment_id is not None
            and recruitment is not None
            and recruitment.deleted_at is None
        )

    def get_permissions(self, announcement) -> dict:
        """输出当前用户的操作入口权限，区分本人删除与治理删除。

        Sprint3 起公告不可编辑，can_edit 恒为 false。

        Args:
            announcement: 公告实例。

        Returns:
            dict: can_edit、can_delete、can_govern_delete。
        """
        user = self.context["request"].user
        is_admin = bool(getattr(user, "is_admin", False))
        is_author = announcement.author_id == user.pk
        return {
            "can_edit": False,
            "can_delete": is_admin and is_author,
            "can_govern_delete": is_admin,
        }


class SubmissionSerializer(serializers.ModelSerializer):
    """本人投稿输出：内容、状态、驳回理由与生成公告引用。"""

    class Meta:
        model = AnnouncementSubmission
        fields = (
            "id", "title", "content", "time_kind", "event_at", "link_url",
            "status", "submitted_at", "reviewed_at", "reject_reason", "announcement_id",
        )
        read_only_fields = fields


class AdminSubmissionSerializer(serializers.ModelSerializer):
    """待审池输出：投稿人、领取信息与逾期标记。"""

    submitter = serializers.SerializerMethodField()
    claimed_by = serializers.SerializerMethodField()
    overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = AnnouncementSubmission
        fields = (
            "id", "title", "content", "time_kind", "event_at", "link_url",
            "submitted_at", "submitter", "claimed_by", "claimed_until", "overdue",
        )
        read_only_fields = fields

    def get_submitter(self, submission) -> dict:
        """投稿人公开信息，仅管理员待审池可见。"""
        return {
            "uid": submission.submitter.uid,
            "nickname": submission.submitter.nickname,
            "role": submission.submitter.role,
        }

    def get_claimed_by(self, submission):
        """当前领取人公开信息；未领取或已交回为 null。"""
        if submission.claimed_by_id is None:
            return None
        return {
            "uid": submission.claimed_by.uid,
            "nickname": submission.claimed_by.nickname,
            "role": submission.claimed_by.role,
        }
