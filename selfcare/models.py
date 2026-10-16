from django.conf import settings
from django.db import models


class SafetyPlan(models.Model):
    """A personal safety plan, written on a good day to use on a hard one.
    Private to its owner: never shown to admins or professionals."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="safety_plan")
    warning_signs = models.JSONField(default=list, blank=True)
    coping = models.JSONField(default=list, blank=True)
    distractions = models.JSONField(default=list, blank=True)
    people = models.JSONField(default=list, blank=True)          # [{"name", "phone"}]
    professionals = models.JSONField(default=list, blank=True)   # [{"name", "phone"}]
    reasons = models.JSONField(default=list, blank=True)
    safe_space = models.TextField(blank=True, max_length=1000)
    trusted_name = models.CharField(max_length=60, blank=True)
    trusted_relationship = models.CharField(max_length=30, blank=True)
    trusted_phone = models.CharField(max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
