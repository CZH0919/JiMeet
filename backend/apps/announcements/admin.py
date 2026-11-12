from django.contrib import admin

from apps.announcements.models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    """公告后台入口，便于排查数据。"""

    list_display = ("id", "title", "author", "time_kind", "event_at", "is_pinned", "deleted_at")
    list_filter = ("time_kind", "is_pinned")
    raw_id_fields = ("author", "recruitment")
