from django.test import SimpleTestCase

from apps.core import choices


class ChoicesTest(SimpleTestCase):
    def test_values_match_database_design(self):
        expected = {
            choices.Role: ["student", "teacher"],
            choices.RecruitmentType: ["competition", "activity", "internship"],
            choices.RecruitmentStatus: ["open", "full", "closed"],
            choices.CloseReason: ["deadline", "manual"],
            choices.ApplicationStatus: [
                "processing",
                "accepted",
                "rejected",
                "withdrawn",
                "invalid",
            ],
            choices.PublisherMark: ["none", "hold"],
            choices.ResumeType: ["pdf", "doc", "docx"],
            choices.EmailStatus: ["pending", "sent", "failed"],
        }
        for enum, values in expected.items():
            with self.subTest(enum=enum.__name__):
                self.assertEqual(list(enum.values), values)

    def test_labels_are_chinese(self):
        for enum in (
            choices.Role,
            choices.RecruitmentType,
            choices.RecruitmentStatus,
            choices.CloseReason,
            choices.ApplicationStatus,
            choices.PublisherMark,
            choices.ResumeType,
            choices.EmailStatus,
        ):
            with self.subTest(enum=enum.__name__):
                for member in enum:
                    self.assertTrue(member.label)
