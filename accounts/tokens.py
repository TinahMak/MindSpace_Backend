from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Same mechanism as Django's password-reset tokens, but the hash also
    depends on email_verified — so once a user verifies, any old unverified
    link (already emailed to them, maybe forwarded) stops working."""

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_verified}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()
