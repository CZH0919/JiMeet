from django.test import SimpleTestCase

from apps.core.middleware import (
    REQUEST_ID_HEADER,
    RequestIdLogFilter,
    RequestIdMiddleware,
    current_request_id,
)


def _run(headers=None):
    captured = {}

    def get_response(request):
        captured["request_id"] = request.request_id
        captured["context"] = current_request_id()
        return _Response()

    request = _Request(headers or {})
    response = RequestIdMiddleware(get_response)(request)
    return request, response, captured


class _Request:
    def __init__(self, headers):
        self.headers = headers


class _Response(dict):
    pass


class MiddlewareTest(SimpleTestCase):
    def test_generates_when_absent(self):
        request, response, captured = _run()
        self.assertEqual(len(request.request_id), 32)
        self.assertEqual(response[REQUEST_ID_HEADER], request.request_id)
        self.assertEqual(captured["context"], request.request_id)

    def test_accepts_valid_header(self):
        request, response, _ = _run({REQUEST_ID_HEADER: "abc-123"})
        self.assertEqual(request.request_id, "abc-123")
        self.assertEqual(response[REQUEST_ID_HEADER], "abc-123")

    def test_rejects_invalid_header(self):
        for bad in ("a" * 65, "bad value", "中文", "a;b"):
            with self.subTest(bad=bad):
                request, _, _ = _run({REQUEST_ID_HEADER: bad})
                self.assertNotEqual(request.request_id, bad)
                self.assertEqual(len(request.request_id), 32)

    def test_context_reset_after_request(self):
        _run({REQUEST_ID_HEADER: "abc"})
        self.assertEqual(current_request_id(), "-")

    def test_log_filter_injects_request_id(self):
        import logging

        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
        self.assertTrue(RequestIdLogFilter().filter(record))
        self.assertEqual(record.request_id, "-")
