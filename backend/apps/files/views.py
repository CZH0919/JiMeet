"""私有文件流接口，不注册私有目录的静态或媒体路由。"""

from django.http import FileResponse

from apps.core.views import PrivateAPIView
from apps.files.services import download_resume


class ResumeDownloadView(PrivateAPIView):
    def get(self, request, application_id):
        download = download_resume(request.user, application_id)
        try:
            return FileResponse(
                download.stream, as_attachment=True, filename=download.filename,
                content_type=download.content_type,
            )
        except BaseException:
            download.stream.close()
            raise
