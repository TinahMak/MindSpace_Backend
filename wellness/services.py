"""
Pattern analysis over a user's mood history.

This intentionally never outputs a clinical diagnosis or a blunt
"needs help: yes/no" label. It surfaces aggregate patterns (frequency,
trend, common tags) plus a gentle, plain-language reflection, and leaves
what to do with that entirely up to the person reading it.
"""
import logging
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

LOW_MOOD_THRESHOLD = 2  # mood values <= this count as "low" for the ratio calc


def _rule_based_reflection(stats):
    """Fallback wording used if the Gemini call isn't available or fails —
    the insights page should never be empty just because the API hiccuped."""
    if stats["total_entries"] == 0:
        return (
            "There's no mood data in this period yet — check in a few times "
            "and patterns will start to show here."
        )
    if stats["concern_level"] == "elevated":
        return (
            "Your check-ins over this period have leaned quite low quite often. "
            "That doesn't automatically mean anything is wrong — but it might be "
            "worth talking it through with someone you trust, or a professional."
        )
    return (
        "Your mood has been relatively steady over this period. Keep checking in — "
        "noticing patterns early is one of the most useful things this kind of "
        "tracking can do."
    )


def _get_ai_reflection(stats):
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key or stats["total_entries"] == 0:
        return None
    try:
        from google import genai
        from google.genai import types

        prompt = f"""Someone has been tracking their mood in a wellness app. Here is a \
summary of their check-ins over the last {stats['period_days']} days — aggregate stats \
only, not raw entries:
- Total check-ins: {stats['total_entries']}
- Average mood (1=very low, 5=great): {stats['avg_mood']}
- Share of check-ins that were low/very low: {int(stats['low_ratio'] * 100)}%
- Trend: {stats['trend']}
- Most common feelings tagged: {', '.join(stats['top_emotions']) or 'none tagged'}

Write a warm, 2-3 sentence reflection on these patterns for the person to read on their \
dashboard. Rules:
- Never diagnose or name a mental health condition.
- Never claim certainty about how they feel — you only have aggregate numbers, not the \
full picture of their life.
- If the pattern looks concerning (low average, high share of low days, or a declining \
trend), gently suggest it might help to talk to someone — a friend, family member, or a \
professional — without being alarming or clinical.
- If the pattern looks steady or positive, be encouraging without being dismissive.
- Plain, conversational language. No bullet points, no headers, no markdown."""

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=200),
        )
        text = (response.text or "").strip()
        return text or None
    except Exception:
        logger.exception("AI reflection generation failed for mood insights")
        return None


def analyze_mood_patterns(user, days=14):
    from .models import MoodEntry

    cutoff = timezone.localdate() - timedelta(days=days - 1)
    entries = list(MoodEntry.objects.filter(user=user, date__gte=cutoff).order_by("date"))

    total_entries = len(entries)
    avg_mood = round(sum(e.mood for e in entries) / total_entries, 2) if total_entries else None
    low_count = sum(1 for e in entries if e.mood <= LOW_MOOD_THRESHOLD)
    low_ratio = round(low_count / total_entries, 2) if total_entries else 0.0

    trend = "steady"
    if total_entries >= 4:
        midpoint_date = entries[len(entries) // 2].date
        first_half = [e.mood for e in entries if e.date < midpoint_date]
        second_half = [e.mood for e in entries if e.date >= midpoint_date]
        if first_half and second_half:
            delta = (sum(second_half) / len(second_half)) - (sum(first_half) / len(first_half))
            if delta <= -0.75:
                trend = "declining"
            elif delta >= 0.75:
                trend = "improving"

    tag_counts = Counter(tag for e in entries for tag in e.emotions)
    top_emotions = [tag for tag, _ in tag_counts.most_common(3)]

    # Best-effort cross-check against crisis-flagged AI chat messages in the
    # same window. Wrapped defensively so insights never break if the chat
    # app changes shape or isn't present.
    crisis_flag_present = False
    try:
        from aichat.models import Message

        crisis_flag_present = Message.objects.filter(
            conversation__user=user, is_crisis=True, created_at__date__gte=cutoff
        ).exists()
    except Exception:
        logger.exception("Could not check crisis flags for mood insights")

    concern_level = "steady"
    if crisis_flag_present:
        concern_level = "elevated"
    elif total_entries >= 5 and avg_mood is not None and avg_mood <= 2.3:
        concern_level = "elevated"
    elif total_entries >= 5 and low_ratio >= 0.5:
        concern_level = "elevated"
    elif trend == "declining" and total_entries >= 6:
        concern_level = "elevated"

    stats = {
        "period_days": days,
        "total_entries": total_entries,
        "avg_mood": avg_mood,
        "low_ratio": low_ratio,
        "trend": trend,
        "top_emotions": top_emotions,
        "concern_level": concern_level,
        "crisis_flag_present": crisis_flag_present,
    }
    stats["reflection"] = _get_ai_reflection(stats) or _rule_based_reflection(stats)
    return stats
