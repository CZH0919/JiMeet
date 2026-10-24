from django.core.management.base import BaseCommand
from django.db import transaction

from apps.recruitments.models import Tag
from apps.recruitments.seed import PRESET_TAGS


class Command(BaseCommand):
    """幂等写入预设标签和展示顺序，保留已有标签的手工停用状态。"""

    help = "初始化预设领域标签，不重新启用已停用的标签"

    @transaction.atomic
    def handle(self, *args, **options):
        """
        按名称创建或更新预设标签，全部操作在同一事务中提交。

        Params:
            args: Django 管理命令的位置参数，本命令不额外定义参数
            options: Django 的通用命令选项，如 verbosity

        新标签启用，已有标签只更新 sort_order；不会删除自定义标签。
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
