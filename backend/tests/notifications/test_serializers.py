from django.http import QueryDict
from django.test import SimpleTestCase

from apps.notifications.serializers import NotificationQuerySerializer


class NotificationQuerySerializerTest(SimpleTestCase):
    def test_only_literal_boolean_strings_are_accepted(self):
        for value, expected in (("true", True), ("false", False)):
            serializer = NotificationQuerySerializer(data={"is_read": value})
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertIs(serializer.validated_data["is_read"], expected)

        for value in ("", "1", "yes", " true "):
            with self.subTest(value=value):
                serializer = NotificationQuerySerializer(data={"is_read": value})
                self.assertFalse(serializer.is_valid())

    def test_unknown_and_duplicate_query_parameters_are_rejected(self):
        unknown = NotificationQuerySerializer(data={"recipient_id": "1"})
        self.assertFalse(unknown.is_valid())
        duplicate = NotificationQuerySerializer(data=QueryDict("is_read=true&is_read=false"))
        self.assertFalse(duplicate.is_valid())
