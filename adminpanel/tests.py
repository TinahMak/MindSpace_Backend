"""Tests for the Google Drive backup. Google is replaced by a fake, so these
run offline and never touch a real Drive."""

import io
import json
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from adminpanel import backup
from adminpanel.models import AdminAction, Backup

User = get_user_model()


class FakeResponse:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self._data = data or {}
        self.headers = headers or {}

    def json(self):
        return self._data


class FakeDrive:
    """Stands in for google.auth AuthorizedSession."""

    def __init__(self, email="owner@example.com"):
        self.email = email
        self.uploaded = None
        self.folders = []

    def get(self, url, params=None, **kw):
        if url.endswith("/about"):
            return FakeResponse(data={"user": {"emailAddress": self.email}})
        if url.endswith("/files"):
            return FakeResponse(data={"files": [{"id": f} for f in self.folders]})
        return FakeResponse(404)

    def post(self, url, params=None, headers=None, json=None, **kw):
        if "upload" in url:
            self.meta = json
            return FakeResponse(headers={"Location": "https://upload.example/session"})
        self.folders.append("folder-1")
        return FakeResponse(data={"id": "folder-1"})

    def put(self, url, data=None, headers=None, **kw):
        self.uploaded = data.read()
        return FakeResponse(data={"id": "file-123", "webViewLink": "https://drive.google.com/file/d/file-123/view"})


class BackupTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        Path(self.media.name, "chat_images").mkdir()
        Path(self.media.name, "chat_images", "a.jpg").write_bytes(b"fake-image")
        self.override = override_settings(MEDIA_ROOT=self.media.name, GDRIVE_ACCOUNT_EMAIL="owner@example.com")
        self.override.enable()
        self.owner = User.objects.create_superuser(username="owner@example.com", email="owner@example.com", password="Str0ng!pass123")
        self.staff = User.objects.create_user(username="staff@example.com", email="staff@example.com", password="Str0ng!pass123", is_staff=True)
        self.drive = FakeDrive()
        self.patch = mock.patch.object(backup, "_session", return_value=self.drive)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.override.disable()
        self.media.cleanup()

    def test_backup_uploads_zip_with_data_and_media(self):
        b = backup.run_backup(actor=self.owner)
        self.assertEqual(b.status, Backup.SUCCESS, b.error)
        self.assertEqual(b.drive_account, "owner@example.com")
        self.assertEqual(b.drive_file_id, "file-123")
        self.assertEqual(self.drive.meta["parents"], ["folder-1"])
        z = zipfile.ZipFile(io.BytesIO(self.drive.uploaded))
        names = z.namelist()
        self.assertIn("data.json", names)
        self.assertIn("media/chat_images/a.jpg", names)
        self.assertIn("RESTORE.txt", names)
        data = json.loads(z.read("data.json"))
        self.assertTrue(any(r["model"] == "accounts.user" for r in data))
        self.assertFalse(any(r["model"].startswith("authtoken") for r in data))
        self.assertTrue(AdminAction.objects.filter(action="backup", actor=self.owner).exists())

    def test_wrong_google_account_is_refused(self):
        self.drive.email = "someone.else@gmail.com"
        b = backup.run_backup(actor=self.owner)
        self.assertEqual(b.status, Backup.FAILED)
        self.assertIn("must go to owner@example.com", b.error)
        self.assertIsNone(self.drive.uploaded)

    def test_not_connected_gives_setup_help(self):
        self.patch.stop()
        with override_settings(GDRIVE_TOKEN_FILE=str(Path(self.media.name, "missing.json"))):
            b = backup.run_backup(actor=self.owner)
        self.patch.start()
        self.assertEqual(b.status, Backup.FAILED)
        self.assertIn("gdrive_connect", b.error)

    def test_api_owner_can_run_staff_cannot(self):
        c = APIClient()
        c.force_authenticate(self.staff)
        self.assertEqual(c.get("/api/v1/admin/backup/").status_code, 200)
        self.assertEqual(c.post("/api/v1/admin/backup/").status_code, 403)
        c.force_authenticate(self.owner)
        r = c.post("/api/v1/admin/backup/")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["backup"]["status"], "success")
        r = c.get("/api/v1/admin/backup/")
        self.assertTrue(r.data["can_run"])
        self.assertEqual(len(r.data["backups"]), 1)

    def test_api_blocks_regular_users(self):
        user = User.objects.create_user(username="u@example.com", email="u@example.com", password="Str0ng!pass123")
        c = APIClient()
        c.force_authenticate(user)
        self.assertEqual(c.get("/api/v1/admin/backup/").status_code, 403)

    def test_web_panel_page_and_button(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("adminpanel:backups"))
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse("adminpanel:backup_run"), follow=True)
        self.assertContains(r, "Backup saved to Google Drive")
        self.client.force_login(self.staff)
        r = self.client.post(reverse("adminpanel:backup_run"), follow=True)
        self.assertContains(r, "Only the owner account")
