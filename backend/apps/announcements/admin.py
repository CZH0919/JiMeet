from django.contrib import admin

from apps.announcements.models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    """公告后台入口，仅用于排查数据；编辑与新增入口已收回。"""

    list_display = ("id", "title", "author", "time_kind", "event_at", "is_pinned", "deleted_at")
    list_filter = ("time_kind", "is_pinned")
    raw_id_fields = ("author", "submitted_by", "recruitment")

    def has_add_permission(self, request):
        """禁止后台新增公告。"""
        return False

    def has_change_permission(self, request, obj=None):
        """禁止后台编辑公告（Sprint3 起公告不可编辑）。"""
        return False
