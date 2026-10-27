from django.urls import path

from apps.applications import views

urlpatterns = [
    path("recruitments/<int:recruitment_id>/applications", views.RecruitmentApplicationListView.as_view(), name="recruitment-applications"),
    path("me/applications", views.MyApplicationListView.as_view(), name="my-applications"),
    path("applications/<int:application_id>", views.ApplicationDetailView.as_view(), name="application-detail"),
    path("applications/<int:application_id>/withdraw", views.ApplicationActionView.as_view(action="withdraw"), name="application-withdraw"),
    path("applications/<int:application_id>/accept", views.ApplicationActionView.as_view(action="accept"), name="application-accept"),
    path("applications/<int:application_id>/reject", views.ApplicationActionView.as_view(action="reject"), name="application-reject"),
    path("applications/<int:application_id>/hold", views.ApplicationActionView.as_view(action="hold"), name="application-hold"),
    path("applications/<int:application_id>/unhold", views.ApplicationActionView.as_view(action="unhold"), name="application-unhold"),
    path("applications/<int:application_id>/read", views.ApplicationActionView.as_view(action="read"), name="application-read"),
]
