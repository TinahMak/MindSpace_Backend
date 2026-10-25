"""
Google Drive backup for MindSpace.

What a backup contains (one .zip file):
  * data.json      every database table, in Django's own format, so it can be
                   restored with `python manage.py loaddata data.json`
  * media/...      every uploaded file (chat photos, professionals' documents)
  * manifest.json  when it was made and what is inside
  * RESTORE.txt    how to put it back

Login tokens and sessions are left out on purpose: they are passwords in all
but name, and people simply log in again after a restore.

Google Drive access uses the person's own Google account (OAuth). It is set
up once from the terminal with `python manage.py gdrive_connect`, which saves
a token file next to manage.py. That file is in .gitignore and must never be
committed. The app only asks for the "drive.file" permission, which means it
can see and change only the files it created itself (the backups), nothing
else in that Drive.
"""

import io
import json
import logging
import os
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from .models import Backup

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"

# Left out of data.json (see module docstring). contenttypes and permissions
# are recreated automatically by `migrate`.
EXCLUDE = [
    "contenttypes",
    "auth.permission",
    "sessions",
    "admin.logentry",
    "authtoken",
]

CONNECT_HELP = (
    "Google Drive isn't connected yet. On the computer that runs Django, open a terminal in "
    "mindspace_backend and run:  python manage.py gdrive_connect"
)


class BackupError(Exception):
    """Something went wrong; the message is safe to show an admin."""


# ── settings ────────────────────────────────────────────────────────────

def _setting(name, default=""):
    return getattr(settings, name, None) or os.environ.get(name) or default


def _path(name, default):
    p = Path(_setting(name, default))
    return p if p.is_absolute() else Path(settings.BASE_DIR) / p


def client_secret_path():
    return _path("GDRIVE_CLIENT_SECRET_FILE", "gdrive_client_secret.json")


def token_path():
    return _path("GDRIVE_TOKEN_FILE", "gdrive_token.json")


def expected_account():
    return (_setting("GDRIVE_ACCOUNT_EMAIL") or "").strip().lower()


def folder_name():
    return _setting("GDRIVE_FOLDER_NAME", "MindSpace Backups")


def can_run(user):
    """Backups hold everyone's private data, so only owner accounts
    (superusers) may start one. Other admins can see the history."""
    return bool(user and user.is_authenticated and user.is_active and user.is_superuser)


# ── Google credentials ──────────────────────────────────────────────────

def _read_token_file():
    p = token_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_token_file(creds, account):
    data = json.loads(creds.to_json())
    data["mindspace_account"] = account
    p = token_path()
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)  # readable by this user only (no effect on Windows)
    except OSError:
        pass


def _credentials():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    data = _read_token_file()
    if not data:
        raise BackupError(CONNECT_HELP)
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise BackupError(CONNECT_HELP)
        try:
            creds.refresh(Request())
        except RefreshError:
            raise BackupError(
                "Google Drive access has expired or was removed. Reconnect it with:  python manage.py gdrive_connect"
            )
        _write_token_file(creds, data.get("mindspace_account", ""))
    return creds


def _session():
    from google.auth.transport.requests import AuthorizedSession

    return AuthorizedSession(_credentials())


def _account_email(session):
    r = session.get(f"{DRIVE}/about", params={"fields": "user(emailAddress)"}, timeout=30)
    if r.status_code != 200:
        raise BackupError(f"Google Drive said no ({r.status_code}). Try reconnecting with: python manage.py gdrive_connect")
    return (r.json().get("user", {}).get("emailAddress") or "").lower()


def _check_account(email):
    want = expected_account()
    if want and email != want:
        raise BackupError(
            f"Google Drive is connected to {email}, but backups must go to {want}. "
            "Run  python manage.py gdrive_connect  again and choose the right account."
        )


def connect_interactive(email_hint="", port=0):
    """Used by `manage.py gdrive_connect`. Opens Google's sign-in page in a
    browser on this computer, then saves the token. Returns the account email."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret = client_secret_path()
    if not secret.exists():
        raise BackupError(
            f"Missing {secret.name}. Download the OAuth client file (type: Desktop app) from Google Cloud "
            f"Console and save it as:\n  {secret}"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    kwargs = {"prompt": "consent", "access_type": "offline"}
    hint = (email_hint or expected_account()).strip()
    if hint:
        kwargs["login_hint"] = hint
    creds = flow.run_local_server(port=port, open_browser=True, **kwargs)

    from google.auth.transport.requests import AuthorizedSession

    email = _account_email(AuthorizedSession(creds))
    want = (email_hint or expected_account()).strip().lower()
    if want and email != want:
        raise BackupError(f"You signed in as {email}, but backups must go to {want}. Nothing was saved; run it again.")
    _write_token_file(creds, email)
    return email


def disconnect():
    p = token_path()
    if p.exists():
        p.unlink()


def status():
    data = _read_token_file()
    return {
        "configured": client_secret_path().exists(),
        "connected": bool(data and data.get("refresh_token")),
        "account": (data or {}).get("mindspace_account", ""),
        "expected_account": expected_account(),
        "folder": folder_name(),
    }


# ── building the archive ────────────────────────────────────────────────

def _build_zip(path):
    """Write the backup zip to `path`. Returns (records, media_files)."""
    buf = io.StringIO()
    call_command(
        "dumpdata",
        exclude=EXCLUDE,
        natural_foreign=True,
        indent=None,
        stdout=buf,
    )
    data = buf.getvalue()
    records = len(json.loads(data)) if data.strip() else 0

    media_root = Path(settings.MEDIA_ROOT)
    media_files = 0
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        z.writestr("data.json", data)
        if media_root.exists():
            for f in sorted(media_root.rglob("*")):
                if f.is_file():
                    z.write(f, arcname=str(Path("media") / f.relative_to(media_root)))
                    media_files += 1
        z.writestr(
            "manifest.json",
            json.dumps(
                {
                    "app": "MindSpace",
                    "created_at": timezone.now().isoformat(),
                    "database_engine": settings.DATABASES["default"]["ENGINE"],
                    "records": records,
                    "media_files": media_files,
                    "excluded": EXCLUDE,
                },
                indent=2,
            ),
        )
        z.writestr("RESTORE.txt", RESTORE_TEXT)
    return records, media_files


RESTORE_TEXT = """How to restore this MindSpace backup
=====================================

1. Unzip this file somewhere.
2. In mindspace_backend, point .env at the database you want to restore into
   (an EMPTY database is best), then create the tables:
       python manage.py migrate
3. Load the data:
       python manage.py loaddata /path/to/unzipped/data.json
4. Copy the unzipped "media" folder over mindspace_backend/media.
5. Everyone logs in again (login tokens are not stored in backups).
"""


# ── uploading ───────────────────────────────────────────────────────────

def _folder_id(session):
    name = folder_name().replace("\\", "\\\\").replace("'", "\\'")
    q = f"name = '{name}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    r = session.get(f"{DRIVE}/files", params={"q": q, "spaces": "drive", "fields": "files(id)"}, timeout=30)
    if r.status_code != 200:
        raise BackupError(f"Couldn't look up the backup folder on Google Drive ({r.status_code}).")
    files = r.json().get("files", [])
    if files:
        return files[0]["id"]
    r = session.post(f"{DRIVE}/files", json={"name": folder_name(), "mimeType": FOLDER_MIME}, params={"fields": "id"}, timeout=30)
    if r.status_code not in (200, 201):
        raise BackupError(f"Couldn't create the backup folder on Google Drive ({r.status_code}).")
    return r.json()["id"]


def _upload(session, path, name, folder):
    size = os.path.getsize(path)
    start = session.post(
        f"{UPLOAD}/files",
        params={"uploadType": "resumable", "fields": "id,webViewLink"},
        headers={"X-Upload-Content-Type": "application/zip", "X-Upload-Content-Length": str(size)},
        json={"name": name, "parents": [folder], "description": "MindSpace backup (database + uploaded files)"},
        timeout=60,
    )
    if start.status_code != 200 or "Location" not in start.headers:
        raise BackupError(f"Google Drive wouldn't start the upload ({start.status_code}).")
    with open(path, "rb") as fh:
        done = session.put(
            start.headers["Location"],
            data=fh,
            headers={"Content-Type": "application/zip", "Content-Length": str(size)},
            timeout=60 * 30,
        )
    if done.status_code not in (200, 201):
        raise BackupError(f"The upload to Google Drive failed ({done.status_code}).")
    info = done.json()
    return info["id"], info.get("webViewLink", ""), size


# ── the whole job ───────────────────────────────────────────────────────

def run_backup(actor=None):
    """Make a backup and upload it. Always returns the Backup row (check its
    status). Raises BackupError only if a backup is already running."""
    from . import services as svc

    with transaction.atomic():
        stale = timezone.now() - timedelta(minutes=45)
        Backup.objects.filter(status=Backup.RUNNING, started_at__lt=stale).update(
            status=Backup.FAILED, error="Stopped before it finished.", finished_at=timezone.now()
        )
        if Backup.objects.select_for_update().filter(status=Backup.RUNNING).exists():
            raise BackupError("A backup is already running. Give it a minute, then refresh.")
        b = Backup.objects.create(started_by=actor, started_by_email=getattr(actor, "email", "") or "")

    stamp = timezone.localtime().strftime("%Y-%m-%d_%H-%M-%S")
    b.filename = f"mindspace-backup-{stamp}.zip"
    try:
        session = _session()
        account = _account_email(session)
        _check_account(account)
        b.drive_account = account
        with tempfile.TemporaryDirectory(prefix="mindspace-backup-") as tmp:
            path = os.path.join(tmp, b.filename)
            b.records, b.media_files = _build_zip(path)
            b.drive_file_id, b.drive_link, b.size_bytes = _upload(session, path, b.filename, _folder_id(session))
        b.status = Backup.SUCCESS
    except BackupError as e:
        b.status, b.error = Backup.FAILED, str(e)
    except Exception as e:  # network trouble, disk full, ...
        logger.exception("Backup failed")
        b.status, b.error = Backup.FAILED, f"Unexpected error: {e.__class__.__name__}: {e}"[:2000]
    b.finished_at = timezone.now()
    b.save()

    if actor is not None:
        detail = f"{b.filename} → {b.drive_account}" if b.status == Backup.SUCCESS else f"failed: {b.error}"
        svc.log(actor, "backup", detail=detail)
    return b


def backup_dict(b):
    return {
        "id": b.id,
        "status": b.status,
        "filename": b.filename,
        "size_bytes": b.size_bytes,
        "records": b.records,
        "media_files": b.media_files,
        "drive_account": b.drive_account,
        "drive_link": b.drive_link,
        "error": b.error,
        "started_by": b.started_by_email or "terminal",
        "started_at": b.started_at,
        "finished_at": b.finished_at,
    }


def history(limit=20):
    return list(Backup.objects.all()[:limit])
