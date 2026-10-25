from django.core.management.base import BaseCommand, CommandError

from adminpanel import backup


class Command(BaseCommand):
    help = "Connect MindSpace backups to a Google Drive account (one-time setup). Opens a browser to sign in."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="", help="Google account that must receive the backups (defaults to GDRIVE_ACCOUNT_EMAIL in .env).")
        parser.add_argument("--port", type=int, default=0, help="Local port for Google's sign-in redirect (default: any free port).")
        parser.add_argument("--disconnect", action="store_true", help="Forget the saved Google Drive connection.")

    def handle(self, *args, **opts):
        if opts["disconnect"]:
            backup.disconnect()
            self.stdout.write(self.style.SUCCESS("Google Drive disconnected (token file removed)."))
            return
        self.stdout.write("A browser window will open. Sign in with the Google account that should receive the backups,")
        self.stdout.write("then allow MindSpace to create files in your Google Drive.\n")
        try:
            email = backup.connect_interactive(email_hint=opts["email"], port=opts["port"])
        except backup.BackupError as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS(f"Connected. Backups will go to {email}, folder \"{backup.folder_name()}\"."))
        self.stdout.write(f"Token saved to {backup.token_path()} (keep it private, never commit it).")
