from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings

from apps.applications.models import Application, PrivateResumeStorage


class PrivateResumeStorageTest(SimpleTestCase):
    def test_uses_private_root_and_rejects_public_url(self):
        storage = Application._meta.get_field("resume_file").storage
        for _ in range(2):
            with TemporaryDirectory() as directory, override_settings(
                PRIVATE_FILE_ROOT=Path(directory),
            ):
                name = storage.save("resumes/test.pdf", ContentFile(b"%PDF-test"))
                self.assertEqual(Path(storage.path(name)), Path(directory) / name)
                with storage.open(name, "rb") as resume:
                    self.assertEqual(resume.read(), b"%PDF-test")
                with self.assertRaises(ValueError):
                    storage.url(name)

    def test_private_storage_serializes_without_machine_path(self):
        path, args, kwargs = PrivateResumeStorage().deconstruct()
        self.assertEqual(path, "apps.applications.models.PrivateResumeStorage")
        self.assertEqual(args, ())
        self.assertEqual(kwargs, {})
