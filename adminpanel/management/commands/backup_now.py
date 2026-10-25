from django.core.management.base import BaseCommand, CommandError

from adminpanel import backup


class Command(BaseCommand):
    help = "Back up the MindSpace database and uploaded files to Google Drive now."

    def handle(self, *args, **opts):
        self.stdout.write("Backing up to Google Drive…")
        try:
            b = backup.run_backup(actor=None)
        except backup.BackupError as e:
            raise CommandError(str(e))
        if b.status != b.SUCCESS:
            raise CommandError(b.error)
        self.stdout.write(self.style.SUCCESS(
            f"Done: {b.filename} ({b.size_bytes / 1024 / 1024:.1f} MB, {b.records} records, "
            f"{b.media_files} files) uploaded to {b.drive_account}."
        ))
        if b.drive_link:
            self.stdout.write(f"Open it: {b.drive_link}")
