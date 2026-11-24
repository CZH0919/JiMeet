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
from apps.announcements.models import Announcement


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


class AnnouncementUpdateSerializer(StrictSerializer):
    """编辑公告的部分更新字段；至少提供一个可写字段。"""

    title = StrictCharField(min_length=1, max_length=100, required=False)
    content = StrictCharField(min_length=1, max_length=5000, required=False)
    time_kind = serializers.ChoiceField(choices=AnnouncementTimeKind.values, required=False)
    event_at = AwareDateTimeField(required=False)
    link_url = StrictCharField(max_length=500, required=False, allow_null=True)
    recruitment_id = StrictIntegerField(required=False, allow_null=True, min_value=1)

    def validate_link_url(self, value):
        """校验相关链接格式。"""
        return _validate_link_url(value)

    def validate(self, attrs):
        """拒绝空更新。

        Args:
            attrs: 已校验字段映射。

        Returns:
            dict: 含至少一个字段的映射。

        Raises:
            serializers.ValidationError: 未提供任何可写字段。
        """
        if not attrs:
            raise serializers.ValidationError("至少提供一个可写字段")
        return attrs


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

        Args:
            announcement: 公告实例。

        Returns:
            dict: can_edit、can_delete、can_govern_delete。
        """
        user = self.context["request"].user
        is_admin = bool(getattr(user, "is_admin", False))
        is_author = announcement.author_id == user.pk
        return {
            "can_edit": is_admin and is_author,
            "can_delete": is_admin and is_author,
            "can_govern_delete": is_admin,
        }
