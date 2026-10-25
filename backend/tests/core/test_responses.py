from django.test import SimpleTestCase

from apps.core.errors import ErrorCode
from apps.core.responses import created, ok, page


class EnvelopeTest(SimpleTestCase):
    def test_ok_envelope_keys(self):
        response = ok({"a": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data), {"code", "message", "data", "request_id"}
        )
        self.assertEqual(response.data["code"], ErrorCode.OK)
        self.assertEqual(response.data["data"], {"a": 1})

    def test_created_uses_201(self):
        response = created({"id": 1})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["code"], ErrorCode.OK)

    def test_page_shape(self):
        response = page([{"id": 1}], 2, 20, 41)
        data = response.data["data"]
        self.assertEqual(data["items"], [{"id": 1}])
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["page_size"], 20)
        self.assertEqual(data["total"], 41)
