from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("notifications", views.NotificationListView.as_view(), name="notification-list"),
    path("notifications/unread-count", views.NotificationUnreadCountView.as_view(), name="notification-unread-count"),
    path("notifications/<int:notification_id>/read", views.NotificationReadView.as_view(), name="notification-read"),
    path("notifications/read-all", views.NotificationReadAllView.as_view(), name="notification-read-all"),
]
