# Update v20: Google Drive backups

Admins now have a **Backups** page (web panel: `/panel/backups/`; mobile:
Admin → Settings → Backup to Google Drive). One tap copies the whole database
and all uploaded files into a `MindSpace Backups` folder in Google Drive.

- Only **owner accounts (superusers)** can start a backup, because a backup
  holds everyone's private data. Other admins can see the history.
- MindSpace only asks Google for the `drive.file` permission: it can see and
  change only the backup files it created, nothing else in that Drive.
- Backups go only to the account in `GDRIVE_ACCOUNT_EMAIL`. If Drive is
  connected to any other account, the backup is refused.
- Every backup is written to the audit log.
- Login tokens and sessions are not included (everyone logs in again after a
  restore). `RESTORE.txt` inside each zip explains how to restore.

## One-time Google setup (about 10 minutes)

1. Go to https://console.cloud.google.com and sign in as
   chriemakocheredze@gmail.com. Create a project called `MindSpace`.
2. **APIs & Services → Library** → search **Google Drive API** → **Enable**.
3. **Google Auth Platform** (also called "OAuth consent screen") → **Get started**:
   app name `MindSpace`, your email as support email, audience **External**,
   your email as contact. Finish.
4. **Audience** → **Publish app** (move it from Testing to In production).
   Do this: while an app is in "Testing", Google expires the Drive connection
   every 7 days. If Google asks, you can stay in Testing instead and add
   chriemakocheredze@gmail.com under **Test users**, but then you must run
   `gdrive_connect` again every week.
5. **Clients** → **Create client** → type **Desktop app** → name it
   `MindSpace backups` → **Create** → **Download JSON**.
6. Rename that file to `gdrive_client_secret.json` and put it in
   `mindspace_backend/` (next to `manage.py`). It is in `.gitignore`.
7. Add this line to `mindspace_backend/.env`:

       GDRIVE_ACCOUNT_EMAIL=chriemakocheredze@gmail.com

8. Connect (a browser opens; sign in and click Allow; if Google shows
   "Google hasn't verified this app", click **Advanced → Go to MindSpace**,
   since it is your own app):

       python manage.py gdrive_connect

   This saves `gdrive_token.json` next to `manage.py`. Keep it private and
   never commit it (it is in `.gitignore`).

## Using it

- Web: log in as the owner → `/panel/backups/` → **Back up to Google Drive now**.
- Mobile: Admin → Settings → **Backup to Google Drive** → **Back up now**.
- Terminal: `python manage.py backup_now` (handy for a scheduled job).
- Disconnect: `python manage.py gdrive_connect --disconnect`.

Make sure the account you use is a superuser. To make one:
`python manage.py createsuperuser`.

## Files in this update

New: `adminpanel/backup.py`, `adminpanel/management/commands/gdrive_connect.py`,
`adminpanel/management/commands/backup_now.py`,
`adminpanel/migrations/0002_backup.py`,
`adminpanel/templates/adminpanel/backups.html`, `adminpanel/tests.py`.

Changed: `adminpanel/models.py`, `adminpanel/views.py`, `adminpanel/urls.py`,
`adminpanel/api.py`, `adminpanel/templates/adminpanel/base.html`,
`api/urls.py`, `requirements.txt`, `.gitignore`, `.env.example`.
