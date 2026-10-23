from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.errors import ValidationFailed
from apps.core.pagination import paginate


class _FakeQuerySet:
    def __init__(self, items):
        self._items = items

    def count(self):
        return len(self._items)

    def __getitem__(self, key):
        return self._items[key]


def _request(**params):
    factory = APIRequestFactory()
    return Request(factory.get("/", params))


class PaginationTest(SimpleTestCase):
    def test_defaults(self):
        items, page_number, page_size, total = paginate(_FakeQuerySet(list(range(30))), _request())
        self.assertEqual(page_number, 1)
        self.assertEqual(page_size, 20)
        self.assertEqual(total, 30)
        self.assertEqual(len(items), 20)

    def test_second_page(self):
        items, page_number, page_size, _ = paginate(
            _FakeQuerySet(list(range(30))), _request(page=2, page_size=10)
        )
        self.assertEqual((page_number, page_size), (2, 10))
        self.assertEqual(items, list(range(10, 20)))

    def test_page_size_upper_bound(self):
        with self.assertRaises(ValidationFailed):
            paginate(_FakeQuerySet([]), _request(page_size=51))

    def test_invalid_values(self):
        for params in ({"page": "abc"}, {"page": "0"}, {"page_size": "-1"}, {"page_size": "x"}):
            with self.subTest(params=params):
                with self.assertRaises(ValidationFailed):
                    paginate(_FakeQuerySet([]), _request(**params))
