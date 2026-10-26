from django.urls import path

from apps.applications import views

urlpatterns = [
    path("recruitments/<int:recruitment_id>/applications", views.RecruitmentApplicationListView.as_view(), name="recruitment-applications"),
    path("me/applications", views.MyApplicationListView.as_view(), name="my-applications"),
    path("applications/<int:application_id>", views.ApplicationDetailView.as_view(), name="application-detail"),
]
