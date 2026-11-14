"""长期申请查询、简历归属及上传边界回归。"""
import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.applications.models import Application, ApplicationStatusHistory
from apps.files.storage import save_resume
from apps.recruitments.services import delete_recruitment
from apps.core import clock
from tests.base import TxTestCase
from tests.factories import make_application, make_recruitment, make_user


def pdf_file(size=64):
    prefix = b"%PDF-1.7\n"
    return SimpleUploadedFile("resume.pdf", prefix + b"x" * (size - len(prefix)), content_type="application/pdf")


class ResumeAccessStage4Test(TxTestCase):
    def setUp(self):
        super().setUp()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        override = override_settings(PRIVATE_FILE_ROOT=self.root)
        override.enable(); self.addCleanup(override.disable)
        self.publisher, self.applicant = make_user(), make_user()
        self.admin = make_user(is_admin=True)

    def _application(self, recruitment, user, status="processing", **fields):
        stored = save_resume(pdf_file())
        return make_application(
            recruitment, user, status=status, resume_file=stored.path,
            resume_name=stored.original_name, resume_size=stored.size, resume_type=stored.type, **fields,
        )

    def _download(self, user, app, expected):
        self.login(user)
        response = self.client.get(f"/api/v1/applications/{app.pk}/resume")
        self.assertEqual(response.status_code, expected)
        if expected == 200:
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
        response.close()

    def test_long_term_records_remain_visible_only_to_participants(self):
        for age in (179, 180, 181, 730):
            with self.subTest(age=age):
                old = clock.now() - timedelta(days=age)
                r = make_recruitment(self.publisher, status="closed", closed_at=old, close_reason="manual", accepted_count=1)
                app = self._application(r, self.applicant, status="accepted", created_at=old)
                self.login(self.applicant)
                result = self.client.get("/api/v1/me/applications", {"recruitment_id": r.pk, "status": "accepted"})
                self.assertEqual((result.status_code, result.data["data"]["total"]), (200, 1))
                self._download(self.applicant, app, 200)
                self._download(self.publisher, app, 200)
                response = self.client.get(f"/api/v1/recruitments/{r.pk}/applications")
                self.assertEqual((response.status_code, response.data["data"]["total"]), (200, 1))
                self._download(self.admin, app, 404)

    def test_withdrawal_retains_own_file_and_reapplication_creates_new_record(self):
        r = make_recruitment(self.publisher)
        self.login(self.applicant)
        created = self.client.post(f"/api/v1/recruitments/{r.pk}/applications", {"resume": pdf_file()}, format="multipart")
        self.assertEqual(created.status_code, 201)
        old = Application.objects.get(pk=created.data["data"]["id"])
        self.assertEqual(self.client.post(f"/api/v1/applications/{old.pk}/withdraw", {}, format="json").status_code, 200)
        self._download(self.applicant, old, 200)
        self._download(self.publisher, old, 403)
        self.login(self.applicant)
        created = self.client.post(f"/api/v1/recruitments/{r.pk}/applications", {"resume": pdf_file()}, format="multipart")
        self.assertEqual(created.status_code, 201)
        self.assertNotEqual(created.data["data"]["id"], old.pk)
        old.refresh_from_db()
        self.assertEqual(old.status, "withdrawn")
        self.assertTrue((self.root / old.resume_file.name).exists())
        self.assertEqual(old.status_history.get().reason, "withdraw")

    def test_deletion_revokes_all_publisher_files_including_rejected(self):
        r = make_recruitment(self.publisher, accepted_count=1)
        rows = [(make_user(), status) for status in ("processing", "accepted", "rejected", "withdrawn", "invalid")]
        apps = [(user, self._application(r, user, status=status)) for user, status in rows]
        delete_recruitment(self.publisher, r.pk)
        for user, app in apps:
            with self.subTest(original_status=app.status):
                self._download(user, app, 200)
                self._download(self.publisher, app, 403)
                detail = self.client.get(f"/api/v1/applications/{app.pk}")
                self.assertEqual(detail.status_code, 200)
                self.assertNotIn("resume", detail.data["data"])
                self.assertNotIn("note", detail.data["data"])
                self._download(self.admin, app, 404)
        self.assertEqual(ApplicationStatusHistory.objects.filter(reason="delete_invalid").count(), 2)
        self.assertEqual(self.client.get(f"/api/v1/recruitments/{r.pk}").status_code, 404)

    def test_upload_size_and_note_limits_leave_no_partial_application(self):
        r = make_recruitment(self.publisher)
        self.login(self.applicant)
        for upload, note in ((pdf_file(10 * 1024 * 1024 + 1), ""), (pdf_file(), "字" * 1001)):
            response = self.client.post(f"/api/v1/recruitments/{r.pk}/applications", {"resume": upload, "note": note}, format="multipart")
            self.assertEqual(response.status_code, 400)
            self.assertFalse(Application.objects.exists())
            self.assertFalse(any(path.is_file() for path in self.root.rglob("*")))
        response = self.client.post(f"/api/v1/recruitments/{r.pk}/applications", {"resume": pdf_file(10 * 1024 * 1024), "note": "字" * 1000}, format="multipart")
        self.assertEqual(response.status_code, 201)
        app = Application.objects.get()
        original = app.note
        response = self.client.patch(f"/api/v1/applications/{app.pk}", {"note": "字" * 1001}, format="multipart")
        self.assertEqual(response.status_code, 400)
        app.refresh_from_db()
        self.assertEqual(app.note, original)
