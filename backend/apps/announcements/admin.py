from django.contrib import admin

from apps.announcements.models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    """公告只读后台。业务删除由带通知与审计的公告服务处理。"""

    list_display = ("id", "title", "author", "time_kind", "event_at", "is_pinned", "deleted_at")
    list_filter = ("time_kind", "is_pinned")
    raw_id_fields = ("author", "submitted_by", "recruitment")

    def has_add_permission(self, request):
        """禁止后台新增公告。"""
        return False

    def has_change_permission(self, request, obj=None):
        """禁止后台修改公告正文。"""
        return False

    def has_delete_permission(self, request, obj=None):
        """禁止后台单条及批量物理删除公告。"""
        return False
