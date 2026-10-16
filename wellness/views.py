from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from .models import WeeklyInsight
from .report import build_mood_report_pdf
from .services import analyze_mood_patterns

VALID_PERIODS = (7, 14, 30)


def _clean_days(request):
    try:
        days = int(request.GET.get("days", 14))
    except (TypeError, ValueError):
        days = 14
    return days if days in VALID_PERIODS else 14


@login_required
def insights_view(request):
    days = _clean_days(request)
    stats = analyze_mood_patterns(request.user, days=days)
    latest_weekly = WeeklyInsight.objects.filter(user=request.user).order_by("-period_end").first()
    context = {
        "stats": stats,
        "days": days,
        "periods": VALID_PERIODS,
        "latest_weekly": latest_weekly,
    }
    return render(request, "wellness/insights.html", context)


@login_required
def download_report_view(request):
    days = _clean_days(request)
    pdf_bytes = build_mood_report_pdf(request.user, days=days)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="mindspace-mood-report-{days}days.pdf"'
    return response


@login_required
def generate_weekly_insight_now_view(request):
    """Runs the weekly-insight logic synchronously, right in the request —
    no Celery worker needed. Useful for trying the feature immediately;
    the Celery beat schedule handles this automatically once it's running."""
    if request.method == "POST":
        from .tasks import _generate_for_user

        _generate_for_user(request.user)
        messages.success(request, "This week's insight has been generated.")
    return redirect("mood_insights")
