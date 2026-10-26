from django.urls import path

from apps.files.views import ResumeDownloadView

urlpatterns = [
    path("applications/<int:application_id>/resume", ResumeDownloadView.as_view(), name="application-resume"),
]
