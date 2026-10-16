from django.contrib import admin

from .models import JournalEntry, MoodEntry, WeeklyInsight


@admin.register(MoodEntry)
class MoodEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "mood", "emotions")
    list_filter = ("mood", "date")
    search_fields = ("user__email",)


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "mood_tag")
    search_fields = ("user__email",)


@admin.register(WeeklyInsight)
class WeeklyInsightAdmin(admin.ModelAdmin):
    list_display = ("user", "period_start", "period_end", "avg_mood", "concern_level", "emailed_at")
    list_filter = ("concern_level",)
    search_fields = ("user__email",)
