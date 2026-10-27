"""通知列表、未读数与显式已读 HTTP 接口。"""

from apps.core import clock
from apps.core.pagination import paginate
from apps.core.responses import ok, page
from apps.core.serializers import EmptyBodySerializer
from apps.core.views import PrivateAPIView, validate_data
from apps.notifications import selectors, services
from apps.notifications.serializers import NotificationQuerySerializer, NotificationSerializer


class NotificationListView(PrivateAPIView):
    query_serializer_class = NotificationQuerySerializer

    def get(self, request):
        queryset = selectors.list_notifications(
            user=request.user, now=clock.now(), is_read=self.query.get("is_read"),
        )
        items, number, size, total = paginate(queryset, request)
        data = NotificationSerializer(items, many=True).data
        return page(data, number, size, total)


class NotificationUnreadCountView(PrivateAPIView):
    def get(self, request):
        count = selectors.list_notifications(
            user=request.user, now=clock.now(), is_read=False,
        ).count()
        return ok({"unread_count": count})


class NotificationReadView(PrivateAPIView):
    def post(self, request, notification_id):
        validate_data(EmptyBodySerializer, request.data)
        notification = services.mark_notification_read(
            user=request.user, notification_id=notification_id, now=clock.now(),
        )
        return ok(NotificationSerializer(notification).data)


class NotificationReadAllView(PrivateAPIView):
    def post(self, request):
        validate_data(EmptyBodySerializer, request.data)
        updated_count = services.mark_all_notifications_read(user=request.user, now=clock.now())
        return ok({"updated_count": updated_count})
