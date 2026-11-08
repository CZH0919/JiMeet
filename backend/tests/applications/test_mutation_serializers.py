from django.test import SimpleTestCase

from apps.applications.serializers import ApplicationActionSerializer, ApplicationUpdateSerializer


class ApplicationMutationSerializerTest(SimpleTestCase):
    def test_patch_requires_note_or_resume_and_rejects_unknown_fields(self):
        for data in ({}, {"status": "accepted"}):
            with self.subTest(data=data):
                serializer = ApplicationUpdateSerializer(data=data)
                self.assertFalse(serializer.is_valid())

    def test_blank_note_means_clear_and_resume_is_optional(self):
        serializer = ApplicationUpdateSerializer(data={"note": ""})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["note"])

    def test_read_requires_timezone_aware_version(self):
        missing = ApplicationActionSerializer(data={}, context={"action": "read"})
        self.assertFalse(missing.is_valid())
        naive = ApplicationActionSerializer(
            data={"seen_updated_at": "2026-10-27T08:00:00"},
            context={"action": "read"},
        )
        self.assertFalse(naive.is_valid())
        aware = ApplicationActionSerializer(
            data={"seen_updated_at": "2026-10-27T08:00:00+08:00"},
            context={"action": "read"},
        )
        self.assertTrue(aware.is_valid(), aware.errors)

    def test_non_read_actions_reject_version_fields(self):
        serializer = ApplicationActionSerializer(
            data={"seen_updated_at": "2026-10-27T08:00:00+08:00"},
            context={"action": "accept"},
        )
        self.assertFalse(serializer.is_valid())
