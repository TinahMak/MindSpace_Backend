from django.conf import settings
from django.db import models
from django.utils import timezone


class MoodEntry(models.Model):
    """A mood check-in. Multiple per day are allowed — moods change
    throughout a day, and forcing one entry/day would hide that."""

    MOOD_CHOICES = [
        (1, "Very low"),
        (2, "Low"),
        (3, "Neutral"),
        (4, "Good"),
        (5, "Great"),
    ]

    MOOD_EMOJI = {
        1: "\U0001F61E",  # 😞
        2: "\U0001F615",  # 😕
        3: "\U0001F610",  # 😐
        4: "\U0001F642",  # 🙂
        5: "\U0001F604",  # 😄
    }

    EMOTION_CHOICES = [
        ("anxious", "Anxious"),
        ("calm", "Calm"),
        ("stressed", "Stressed"),
        ("sad", "Sad"),
        ("happy", "Happy"),
        ("tired", "Tired"),
        ("angry", "Angry"),
        ("hopeful", "Hopeful"),
        ("overwhelmed", "Overwhelmed"),
        ("grateful", "Grateful"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mood_entries"
    )
    date = models.DateField(default=timezone.localdate)
    mood = models.PositiveSmallIntegerField(choices=MOOD_CHOICES)
    emotions = models.JSONField(default=list, blank=True)
    note = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"{self.user} — {self.created_at:%Y-%m-%d %H:%M} — {self.get_mood_display()}"

    @property
    def emoji(self):
        return self.MOOD_EMOJI.get(self.mood, "")


class JournalEntry(models.Model):
    """
    Placeholder for the next build phase (free-form writing + AI analysis).
    Exists now so the dashboard's journal-entry counter has something real
    to query instead of a hardcoded zero.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journal_entries"
    )
    content = models.TextField(blank=True)
    mood_tag = models.CharField(max_length=32, blank=True)
    ai_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.created_at:%Y-%m-%d}"


class WeeklyInsight(models.Model):
    """A snapshot of analyze_mood_patterns() for one user over one 7-day
    window — generated either by the Celery beat schedule (production) or
    the manual 'Generate now' button on the insights page (no broker needed
    for that path, useful for testing before Celery/Redis is set up)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_insights"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total_entries = models.PositiveSmallIntegerField(default=0)
    avg_mood = models.FloatField(null=True, blank=True)
    concern_level = models.CharField(max_length=16, default="steady")
    summary_text = models.TextField(blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end"]

    def __str__(self):
        return f"{self.user} — week of {self.period_start}"
