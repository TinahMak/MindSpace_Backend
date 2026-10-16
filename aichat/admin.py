from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("role", "content", "image", "is_crisis", "created_at")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at", "crisis_messages_30d")
    inlines = [MessageInline]

    def crisis_messages_30d(self, obj):
        """Count of crisis-flagged messages from this user (across all
        their conversations) in the last 30 days — surfaced here for
        manual safety review, not for automated action. We deliberately
        do NOT rate-limit or block crisis-language messages themselves:
        throttling someone reaching out in crisis would be actively
        harmful, so this is a review signal for a human, not a gate."""
        cutoff = timezone.now() - timedelta(days=30)
        return Message.objects.filter(
            conversation__user=obj.user, is_crisis=True, created_at__gte=cutoff
        ).count()

    crisis_messages_30d.short_description = "Crisis msgs (30d)"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "is_crisis", "created_at")
    list_filter = ("role", "is_crisis")
    ordering = ("-is_crisis", "-created_at")
