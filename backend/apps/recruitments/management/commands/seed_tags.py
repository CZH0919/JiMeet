from django.core.management.base import BaseCommand
from django.db import transaction

from apps.recruitments.models import Tag
from apps.recruitments.seed import PRESET_TAGS


class Command(BaseCommand):
    """幂等写入预设标签和展示顺序，保留已有标签的手工停用状态。"""

    help = "初始化预设领域标签，不重新启用已停用的标签"

    @transaction.atomic
    def handle(self, *args, **options):
        """在同一事务内幂等初始化预设标签及顺序。

        新标签启用；已有标签仅更新顺序，保留停用状态及自定义标签。

        Args:
            args: Django 位置参数，本命令未定义额外参数。
            options: Django 通用命令选项。

        Returns:
            None: 向标准输出报告新增数与核对总数。
        """
        created_count = 0
        for sort_order, name in enumerate(PRESET_TAGS):
            _, created = Tag.objects.update_or_create(
                name=name,
                defaults={"sort_order": sort_order},
                create_defaults={"sort_order": sort_order, "is_active": True},
            )
            created_count += int(created)
        self.stdout.write(self.style.SUCCESS(
            f"预设标签初始化完成：新增 {created_count} 个，共核对 {len(PRESET_TAGS)} 个"
        ))
