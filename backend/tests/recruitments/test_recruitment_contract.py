"""招聘类型、补充说明与分页顺序在公开列表和本人视图中的一致性。"""
from datetime import timedelta

from apps.core import clock
from apps.notifications.models import Notification
from apps.recruitments.models import Recruitment
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_tag, make_user


class RecruitmentContractTest(TxTestCase):
    url = "/api/v1/recruitments"

    def setUp(self):
        super().setUp()
        self.owner = make_user()
        self.client.force_authenticate(user=self.owner)
        self.payload = {
            "title": "校内活动", "description": "活动安排", "type": "activity",
            "tag_ids": [make_tag().pk], "max_headcount": 5,
            "deadline": (clock.now() + timedelta(days=3)).isoformat(),
        }

    def test_note_changes_are_distinct_from_application_and_notify_once(self):
        created = self.client.post(self.url, dict(self.payload, note="  周五集合  "), format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["data"]["note"], "周五集合")
        row = Recruitment.objects.get(pk=created.data["data"]["id"])
        applicant = make_user()
        application = make_application(row, applicant, note="本人有相应经验")
        path = f"{self.url}/{row.pk}"
        for body, expected, count in (
            ({"title": row.title}, "周五集合", 0), ({"note": "周五集合"}, "周五集合", 0),
            ({"note": "线上集合"}, "线上集合", 1), ({"note": ""}, None, 2), ({"note": None}, None, 2),
        ):
            response = self.client.patch(path, body, format="json")
            self.assertEqual((response.status_code, response.data["data"]["note"]), (200, expected))
            self.assertEqual(Notification.objects.filter(recipient=applicant, type="recruitment_updated").count(), count)
        self.assertEqual(self.client.patch(path, {"note": "长" * 1001}, format="json").status_code, 400)
        application.refresh_from_db()
        self.assertEqual(application.note, "本人有相应经验")

    def test_legacy_type_reads_filters_and_unchanged_edit(self):
        legacy = make_recruitment(self.owner, type="internship")
        current = make_recruitment(self.owner, type="activity")
        other = make_recruitment(self.owner, type="competition")
        applicant = make_user()
        make_application(legacy, applicant)
        for query, ids in (("activity", {legacy.pk, current.pk}), ("internship", {legacy.pk}),
                           ("competition", {other.pk})):
            items = self.client.get(self.url, {"type": query}).data["data"]["items"]
            self.assertEqual({item["id"] for item in items}, ids)
            self.assertTrue(all(item["type"] != "internship" for item in items))
        url = f"{self.url}/{legacy.pk}"
        result = self.client.get(url).data["data"]
        self.assertEqual((result["type"], result["note"]), ("activity", None))
        self.assertEqual(self.client.post(self.url, dict(self.payload, type="internship"), format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"type": "internship"}, format="json").status_code, 400)
        stamp = legacy.updated_at
        self.assertEqual(self.client.patch(url, {"type": "activity"}, format="json").status_code, 200)
        legacy.refresh_from_db()
        self.assertEqual((legacy.type, legacy.updated_at), ("internship", stamp))
        self.assertFalse(Notification.objects.exists())
        self.client.force_authenticate(user=applicant)
        own = self.client.get("/api/v1/me/applications").data["data"]["items"][0]
        self.assertEqual(own["recruitment"]["type"], "activity")

    def test_effective_status_across_pages_and_tied_publication_times(self):
        now = clock.now()
        first = make_recruitment(self.owner)
        second = make_recruitment(self.owner)
        full = make_recruitment(self.owner, status="full", accepted_count=1, max_headcount=1, full_at=now)
        closed = make_recruitment(self.owner, status="closed", closed_at=now, close_reason="manual")
        expired = make_recruitment(self.owner, deadline=now)
        Recruitment.objects.all().update(created_at=now)
        with self.freeze_at(now):
            for url in (self.url, "/api/v1/me/recruitments"):
                items = []
                for page in (1, 2, 3):
                    items.extend(self.client.get(url, {"page": page, "page_size": 2}).data["data"]["items"])
                self.assertEqual([item["id"] for item in items], [second.pk, first.pk, full.pk, expired.pk, closed.pk])
                self.assertEqual([item["status"] for item in items], ["open", "open", "full", "closed", "closed"])
