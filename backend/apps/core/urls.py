from django.urls import path

from apps.core.health import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
]
