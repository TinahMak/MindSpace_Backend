from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model for MindSpace.

    Extends Django's built-in user with the extra fields collected on the
    3-step signup form (date of birth, phone, focus/reason, marketing opt-in).
    We keep username (inherited) for Django admin compatibility, but
    authentication is done via email in practice.
    """

    FOCUS_CHOICES = [
        ("anxiety_stress", "Managing anxiety or stress"),
        ("mood_tracking", "Tracking my mood"),
        ("habits", "Building healthy habits"),
        ("emotions", "Processing difficult emotions"),
        ("therapy_support", "Support between therapy sessions"),
        ("general_wellness", "General mental wellness"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]

    COUNTRY_CHOICES = [
        ("ZA", "South Africa"),
        ("US", "United States"),
        ("GB", "United Kingdom"),
        ("CA", "Canada"),
        ("AU", "Australia"),
        ("IN", "India"),
        ("OTHER", "Other / not listed"),
    ]

    email = models.EmailField(unique=True)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    focus = models.CharField(max_length=32, choices=FOCUS_CHOICES, blank=True)
    # v11: several reasons can be chosen; `focus` keeps the first one for the website.
    focus_reasons = models.JSONField(default=list, blank=True)
    focus_other = models.CharField(max_length=100, blank=True)
    marketing_opt_in = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)

    email_verified = models.BooleanField(default=False)
    country = models.CharField(max_length=8, choices=COUNTRY_CHOICES, default="ZA")
    weekly_insight_opt_in = models.BooleanField(default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email
