"""请求字段白名单、严格类型与查询参数的通用校验。"""

from datetime import datetime
import re

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    """拒绝未声明的输入字段，避免权限字段被静默忽略。"""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = data.keys() - self.fields.keys()
            if unknown:
                raise serializers.ValidationError({key: "不允许的字段" for key in unknown})
        return super().to_internal_value(data)


class StrictBooleanField(serializers.BooleanField):
    """只接受 JSON 布尔值，不隐式转换字符串或数字。"""

    def to_internal_value(self, data):
        if type(data) is not bool:
            self.fail("invalid", input=data)
        return data


class StrictIntegerField(serializers.IntegerField):
    """只接受 JSON 整数；布尔值、浮点数和数字字符串均拒绝。"""

    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictCharField(serializers.CharField):
    """文本字段不接受数字的隐式字符串转换。"""

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class AwareDateTimeField(serializers.DateTimeField):
    """要求输入显式携带时区，防止截止时间被隐式按服务器时区解释。"""

    def to_internal_value(self, data):
        try:
            parsed = data if isinstance(data, datetime) else parse_datetime(data)
        except (TypeError, ValueError, OverflowError):
            parsed = None
        if parsed is None or timezone.is_naive(parsed):
            raise serializers.ValidationError("须提供带时区的 ISO 8601 时间")
        return super().to_internal_value(data)


class QueryIntegerField(serializers.IntegerField):
    """查询参数允许十进制整数字符串，不接受小数形式。"""

    def to_internal_value(self, data):
        if not isinstance(data, str) or re.fullmatch(r"[0-9]+", data.strip()) is None:
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictQuerySerializer(StrictSerializer):
    """同时拒绝未知键与重复查询键，消除多值参数的解释歧义。"""

    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            repeated = {key: "参数不能重复" for key in data if len(data.getlist(key)) != 1}
            if repeated:
                raise serializers.ValidationError(repeated)
            # 查询空值必须由字段校验，不能沿用 DRF 的 HTML 表单省略空值语义。
            data = dict(data.items())
        return super().to_internal_value(data)


class EmptyQuerySerializer(StrictQuerySerializer):
    """用于没有查询参数的接口。"""


class EmptyBodySerializer(StrictSerializer):
    """用于不接受业务字段的动作接口。"""
