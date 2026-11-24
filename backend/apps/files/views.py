"""私有简历的 HTTP 入口，完整请求与字段契约见 backend/design_file/api.md。"""

from django.http import FileResponse

from apps.core.views import PrivateAPIView
from apps.files.services import download_resume


class ResumeDownloadView(PrivateAPIView):
    def get(self, request, application_id):
        """GET /api/v1/applications/{id}/resume：鉴权下载私有简历。

        成功响应负责关闭文件流；响应构造失败也会关闭句柄。

        Args:
            request: 已认证申请人或发布者请求，不接受查询参数。
            application_id: 路径中的申请主键。

        Returns:
            FileResponse: HTTP 200 的附件文件流，含安全展示名和格式 MIME；不使用 JSON 成功信封，禁止缓存。

        Raises:
            BizError: 对象或文件不存在/不可见时 404；撤回、失效或招聘删除后发布者禁读为 403，本人仍可下载保留文件。
        """
        download = download_resume(request.user, application_id)
        try:
            return FileResponse(
                download.stream, as_attachment=True, filename=download.filename,
                content_type=download.content_type,
            )
        except BaseException:
            download.stream.close()
            raise
