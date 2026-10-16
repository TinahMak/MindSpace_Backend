import logging
from datetime import timedelta

from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .services import analyze_mood_patterns

logger = logging.getLogger(__name__)


def _generate_for_user(user):
    """Core logic, callable directly (no Celery/broker needed) so the
    'Generate now' button on the insights page works even before Celery
    is set up, and so this is unit-testable without a running worker."""
    from .models import MoodEntry, WeeklyInsight

    today = timezone.localdate()
    period_start = today - timedelta(days=6)

    stats = analyze_mood_patterns(user, days=7)

    insight = WeeklyInsight.objects.create(
        user=user,
        period_start=period_start,
        period_end=today,
        total_entries=stats["total_entries"],
        avg_mood=stats["avg_mood"],
        concern_level=stats["concern_level"],
        summary_text=stats["reflection"],
    )

    if user.weekly_insight_opt_in and user.email and stats["total_entries"] > 0:
        try:
            subject = "Your weekly MindSpace mood insight"
            body = render_to_string(
                "wellness/weekly_insight_email.txt", {"user": user, "stats": stats}
            )
            send_mail(subject, body, None, [user.email], fail_silently=True)
            insight.emailed_at = timezone.now()
            insight.save(update_fields=["emailed_at"])
        except Exception:
            logger.exception("Failed to email weekly insight to %s", user.email)

    return insight


@shared_task
def generate_weekly_insight_for_user(user_id):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None
    insight = _generate_for_user(user)
    return insight.pk


@shared_task
def generate_weekly_insights_all_users():
    from django.contrib.auth import get_user_model

    from .models import MoodEntry

    User = get_user_model()
    cutoff = timezone.localdate() - timedelta(days=6)
    user_ids = (
        MoodEntry.objects.filter(date__gte=cutoff)
        .order_by()
        .values_list("user_id", flat=True)
        .distinct()
    )
    count = 0
    for user_id in user_ids:
        generate_weekly_insight_for_user.delay(user_id)
        count += 1
    return count
