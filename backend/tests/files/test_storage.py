import io
import os
import zipfile
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import SimpleTestCase, override_settings

from apps.core import clock
from apps.core.errors import ValidationFailed
from apps.files.storage import cleanup_orphans, discard_resume, open_resume, save_resume, staged_resume
from apps.files.validators import MAX_RESUME_SIZE, clean_resume_name, validate_resume
from tests.base import TxTestCase


def docx_content(valid=True):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        if valid:
            archive.writestr("word/document.xml", "<document/>")
    return content.getvalue()


class StorageTest(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        settings = override_settings(PRIVATE_FILE_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)

    def test_valid_files_and_position(self):
        for extension, content in (("pdf", b"%PDF-test"), ("doc", bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1")),
                                   ("docx", docx_content())):
            with self.subTest(extension=extension):
                upload = SimpleUploadedFile(f"resume.{extension}", content)
                upload.seek(2)
                validate_resume(upload)
                self.assertEqual(upload.tell(), 2)
                stored = save_resume(upload)
                self.assertEqual(upload.tell(), 2)
                self.assertEqual((stored.size, stored.type), (len(content), extension))
                self.assertTrue(stored.path.startswith("resumes/"))
                with open_resume(stored.path) as stream:
                    self.assertEqual(stream.read(), content)
                self.assertTrue(discard_resume(stored.path))
                self.assertTrue(discard_resume(stored.path))

    def test_invalid_files(self):
        cases = (
            ("x.txt", b"text", "type"), ("x.pdf", b"", "size"),
            ("x.pdf", b"%PDF-" + b"x" * MAX_RESUME_SIZE, "size"),
            ("x.pdf", b"text", "signature"), ("x.doc", b"%PDF-test", "signature"),
            ("x.docx", b"PK\x03\x04broken", "signature"), ("x.docx", docx_content(False), "signature"),
        )
        for name, content, reason in cases:
            with self.subTest(name=name, reason=reason), self.assertRaises(ValidationFailed) as caught:
                save_resume(SimpleUploadedFile(name, content))
            self.assertEqual(caught.exception.code, "INVALID_RESUME_FILE")
            self.assertEqual(caught.exception.details, {"reason": reason})
        upload = SimpleUploadedFile("x.pdf", b"x" * (MAX_RESUME_SIZE + 1))
        upload.size = 1
        with self.assertRaises(ValidationFailed) as caught:
            validate_resume(upload)
        self.assertEqual(caught.exception.details, {"reason": "size"})

    def test_names_and_path_escape(self):
        self.assertEqual(clean_resume_name("../folder\\简\x00历.PDF", "pdf"), "简历.pdf")
        self.assertEqual(clean_resume_name(".pdf", "pdf"), "resume.pdf")
        name = clean_resume_name("中" * 255 + ".pdf", "pdf")
        self.assertLessEqual(len(name.encode("utf-8")), 255)
        self.assertTrue(name.endswith(".pdf"))
        for path in ("../escape.pdf", "/tmp/escape.pdf", "resumes/../escape.pdf", "resumes"):
            with self.subTest(path=path), self.assertRaises(PermissionError):
                open_resume(path)
            with self.assertLogs("apps.files.storage", level="WARNING"):
                self.assertFalse(discard_resume(path))
        (self.root / "resumes").mkdir(exist_ok=True)
        try:
            (self.root / "resumes" / "escape").symlink_to(self.root.parent, target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("创建符号链接需要 Windows 开发者模式或提升权限")
            raise
        with self.assertRaises(PermissionError):
            open_resume("resumes/escape/private.pdf")

    def test_save_path_ignores_user_filename(self):
        for name in ("../user_directory/private_resume.pdf", r"..\user_directory\private_resume.pdf"):
            with self.subTest(name=name):
                upload = SimpleUploadedFile("placeholder.pdf", b"%PDF-test")
                # 绕过 Django 上传对象自带的 basename 清洗，直接验证存储层。
                upload._name = name
                stored = save_resume(upload)
                self.assertRegex(stored.path, r"^resumes/[0-9]{4}/[0-9]{2}/[0-9a-f]{32}\.pdf$")
                for fragment in ("..", "\\", "user_directory", "private_resume"):
                    self.assertNotIn(fragment, stored.path)
                self.assertEqual(stored.original_name, "private_resume.pdf")
                self.assertTrue((self.root / stored.path).resolve().is_relative_to((self.root / "resumes").resolve()))
                with open_resume(stored.path) as stream:
                    self.assertEqual(stream.read(), b"%PDF-test")

    def test_staged_and_failed_write_cleanup(self):
        with self.assertRaises(KeyboardInterrupt):
            with staged_resume(SimpleUploadedFile("x.pdf", b"%PDF-test")) as stored:
                self.assertTrue((self.root / stored.path).exists())
                raise KeyboardInterrupt()
        self.assertFalse((self.root / stored.path).exists())
        with mock.patch("apps.files.storage.os.fsync", side_effect=OSError("fsync failed")):
            with self.assertRaises(OSError):
                save_resume(SimpleUploadedFile("x.pdf", b"%PDF-test"))
        self.assertEqual(list((self.root / "resumes").rglob("*.pdf")), [])

    def test_collision_does_not_overwrite_existing_file(self):
        identifier = type("Identifier", (), {"hex": "fixed"})()
        with mock.patch("apps.files.storage.uuid4", return_value=identifier):
            stored = save_resume(SimpleUploadedFile("x.pdf", b"%PDF-first"))
            with self.assertRaises(FileExistsError):
                save_resume(SimpleUploadedFile("x.pdf", b"%PDF-second"))
        with open_resume(stored.path) as stream:
            self.assertEqual(stream.read(), b"%PDF-first")

    def test_failed_orphan_delete_is_reported(self):
        now = clock.now()
        stored = save_resume(SimpleUploadedFile("x.pdf", b"%PDF-test"))
        stamp = (now - timedelta(hours=25)).timestamp()
        os.utime(self.root / stored.path, (stamp, stamp))
        with clock.freeze(now), mock.patch("apps.files.storage.discard_resume", return_value=False):
            report = cleanup_orphans(referenced=lambda paths: set())
        self.assertEqual((report.deleted, report.failed), (0, 1))
        self.assertTrue((self.root / stored.path).exists())

    def test_orphan_age_reference_and_batches(self):
        now = clock.now()
        folder = self.root / "resumes"
        folder.mkdir()
        paths = ["used.pdf", "young.pdf", "boundary.pdf", "orphan.pdf"]
        for name in paths:
            path = folder / name
            path.write_bytes(b"%PDF-test")
            age = 1 if name == "young.pdf" else 24 if name == "boundary.pdf" else 25
            stamp = (now - timedelta(hours=age)).timestamp()
            os.utime(path, (stamp, stamp))
        referenced = mock.Mock(return_value={"resumes/used.pdf"})
        with clock.freeze(now):
            report = cleanup_orphans(referenced=referenced)
        self.assertEqual((report.scanned, report.deleted, report.failed), (4, 1, 0))
        self.assertTrue((folder / "used.pdf").exists())
        self.assertTrue((folder / "young.pdf").exists())
        self.assertTrue((folder / "boundary.pdf").exists())
        self.assertFalse((folder / "orphan.pdf").exists())
        with self.assertRaises(ValueError):
            cleanup_orphans(older_than=timedelta(hours=1), referenced=referenced)
        for index in range(201):
            path = folder / f"batch{index}.pdf"
            path.write_bytes(b"%PDF-test")
            stamp = (now - timedelta(hours=25)).timestamp()
            os.utime(path, (stamp, stamp))
        referenced.reset_mock()
        with clock.freeze(now):
            report = cleanup_orphans(referenced=referenced)
        self.assertEqual(report.deleted, 201)
        self.assertEqual(referenced.call_count, 2)
        self.assertTrue(all(len(call.args[0]) <= 200 for call in referenced.call_args_list))


class StorageTransactionTest(TxTestCase):
    def test_save_requires_outside_transaction(self):
        with transaction.atomic(), self.assertRaises(RuntimeError):
            save_resume(SimpleUploadedFile("x.pdf", b"%PDF-test"))
