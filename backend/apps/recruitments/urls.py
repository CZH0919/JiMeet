"""招募与标签路由，路径不带末尾斜杠。"""

from django.urls import path

from apps.recruitments import views

urlpatterns = [
    path("tags", views.TagListView.as_view(), name="tag-list"),
    path("recruitments", views.RecruitmentListView.as_view(), name="recruitment-list"),
    path("me/recruitments", views.MyRecruitmentListView.as_view(), name="my-recruitment-list"),
    path("recruitments/<int:recruitment_id>", views.RecruitmentDetailView.as_view(), name="recruitment-detail"),
    path("recruitments/<int:recruitment_id>/close", views.RecruitmentCloseView.as_view(), name="recruitment-close"),
]
