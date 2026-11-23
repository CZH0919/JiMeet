"""公告与投稿路由；接口契约见 backend/design_file/api.md 第 8 章。"""
from django.urls import path

from apps.announcements import views

urlpatterns = [
    path("announcements", views.AnnouncementListView.as_view(), name="announcements"),
    path(
        "announcements/<int:announcement_id>",
        views.AnnouncementDetailView.as_view(),
        name="announcement-detail",
    ),
    path(
        "admin/announcements/<int:announcement_id>",
        views.AnnouncementGovernanceView.as_view(),
        name="announcement-governance",
    ),
    path(
        "announcement-submissions",
        views.SubmissionCreateView.as_view(),
        name="announcement-submissions",
    ),
    path(
        "me/announcement-submissions",
        views.MySubmissionListView.as_view(),
        name="my-announcement-submissions",
    ),
    path(
        "admin/announcement-submissions",
        views.AdminSubmissionListView.as_view(),
        name="admin-announcement-submissions",
    ),
    path(
        "admin/announcement-submissions/<int:submission_id>/<str:action>",
        views.AdminSubmissionActionView.as_view(),
        name="admin-announcement-submission-action",
    ),
]
