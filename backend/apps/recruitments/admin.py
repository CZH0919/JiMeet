from django.contrib import admin

from apps.recruitments.models import Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """维护领域标签名称、展示顺序及启停状态。"""

    list_display = ("id", "name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("sort_order", "id")
