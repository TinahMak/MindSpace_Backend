from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """A chat thread. Users typically have one ongoing conversation, but can
    start a fresh one at any time (older ones stay in history, read-only)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation({self.user}, #{self.pk})"

    @property
    def has_crisis_flag(self):
        return self.messages.filter(is_crisis=True).exists()


class Message(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to="chat_images/%Y/%m/", blank=True, null=True)
    is_crisis = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Set on an assistant reply when it followed a user photo: a tentative
    # mood reading the person can choose to log to their mood tracker with
    # one tap. Null/0 means no suggestion was made (e.g. not a personal photo).
    suggested_mood = models.PositiveSmallIntegerField(null=True, blank=True)
    suggested_emotions = models.JSONField(default=list, blank=True)
    mood_logged = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"
