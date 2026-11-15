"""Separate application sessions from the staging gateway's browser Basic auth."""


class StagingSessionStatusMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/v1/') and response.status_code == 401:
            # A browser may discard its cached gateway Basic credentials on any
            # 401, even without a new WWW-Authenticate header. Preserve the API
            # error envelope/code; only the staging transport status is changed.
            response.status_code = 403
            if 'WWW-Authenticate' in response:
                del response['WWW-Authenticate']
            response['Cache-Control'] = 'no-store'
        return response
