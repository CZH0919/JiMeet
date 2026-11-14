"""通知的 HTTP 入口，完整请求与字段契约见 backend/design_file/api.md。

需认证的入口先检查会话和 CSRF，分别拒绝为 401 和 403；非法查询或请求数据通常返回 400，不支持的媒体类型返回 415。异常由统一处理器转换为错误信封；简历下载成功直接返回文件流。
"""

from apps.core.pagination import paginate
from apps.core.responses import ok, page
from apps.core.serializers import EmptyBodySerializer
from apps.core.views import PrivateAPIView, validate_data
from apps.notifications import selectors, services
from apps.notifications.serializers import NotificationQuerySerializer, NotificationSerializer


class NotificationListView(PrivateAPIView):
    query_serializer_class = NotificationQuerySerializer

    def get(self, request):
        """GET /api/v1/notifications：读取本人可见通知。

        Args:
            request: 已认证请求；可传 is_read=true/false、page、page_size。

        Returns:
            Response: HTTP 200，data 为按时间倒序的通知分页，读取不改变已读状态。

        Raises:
            ValidationFailed: 分页参数无效，返回 400。
        """
        queryset = selectors.list_notifications(
            user=request.user, is_read=self.query.get("is_read"),
        )
        items, number, size, total = paginate(queryset, request)
        data = NotificationSerializer(items, many=True).data
        return page(data, number, size, total)


class NotificationUnreadCountView(PrivateAPIView):
    def get(self, request):
        """GET /api/v1/notifications/unread-count：查询本人未读数。

        Args:
            request: 已认证请求，不接受查询参数。

        Returns:
            Response: HTTP 200，data.unread_count 为当前可见的未读通知数量。
        """
        count = selectors.list_notifications(
            user=request.user, is_read=False,
        ).count()
        return ok({"unread_count": count})


class NotificationReadView(PrivateAPIView):
    def post(self, request, notification_id):
        """POST /api/v1/notifications/{id}/read：标记单条通知已读。

        Args:
            request: 已认证写请求，请求体为空或 JSON 空对象。
            notification_id: 路径中的通知主键。

        Returns:
            Response: HTTP 200，data 为通知详情；重复调用保持已读。

        Raises:
            ValidationError: 提供了业务字段，返回 400。
            NotFound: 通知不存在、不属于本人或已不可见，返回 404。
        """
        validate_data(EmptyBodySerializer, request.data)
        notification = services.mark_notification_read(
            user=request.user, notification_id=notification_id,
        )
        return ok(NotificationSerializer(notification).data)


class NotificationReadAllView(PrivateAPIView):
    def post(self, request):
        """POST /api/v1/notifications/read-all：标记本人全部可见通知已读。

        Args:
            request: 已认证写请求，请求体为空或 JSON 空对象。

        Returns:
            Response: HTTP 200，data.updated_count 为本次实际更新数；无新未读时重复调用返回 0。

        Raises:
            ValidationError: 提供了业务字段，返回 400。
        """
        validate_data(EmptyBodySerializer, request.data)
        updated_count = services.mark_all_notifications_read(user=request.user)
        return ok({"updated_count": updated_count})
