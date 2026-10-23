"""健康检查，供运维探活，不要求登录。"""
from django.db import connection
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.errors import ErrorCode
from apps.core.responses import envelope, ok


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return Response(
            envelope(ErrorCode.INTERNAL_ERROR, "数据库不可用"),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return ok({"status": "ok"})
