from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AppRating(models.Model):
    """One rating per person; rating again updates it."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="app_rating"
    )
    stars = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, max_length=1000)
    platform = models.CharField(max_length=16, blank=True)  # android / ios / web
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.stars}★ by {self.user or 'deleted user'}"


class AdminAction(models.Model):
    """Audit log: who did what to whom, and when. Kept even if accounts are deleted."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    actor_email = models.EmailField()
    action = models.CharField(max_length=32)
    target_email = models.EmailField(blank=True)
    detail = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
