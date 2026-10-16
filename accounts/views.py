import json
from collections import Counter
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from wellness.forms import MoodCheckInForm
from wellness.models import JournalEntry, MoodEntry

from .forms import DeleteAccountForm, EmailLoginForm, SignupForm
from .tokens import email_verification_token

User = get_user_model()


def _send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse("verify_email", kwargs={"uidb64": uid, "token": token})
    )
    subject = "Verify your MindSpace email address"
    body = render_to_string(
        "accounts/verification_email.txt", {"user": user, "verify_url": verify_url}
    )
    send_mail(subject, body, None, [user.email], fail_silently=True)


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            _send_verification_email(request, user)
            return redirect("dashboard")
        # Re-render with errors (used for non-JS fallback / server-side errors)
        return render(request, "accounts/signup.html", {"form": form}, status=400)

    form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse("dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        if not self.request.POST.get("remember_me"):
            # Session ends when the browser closes rather than persisting
            # for SESSION_COOKIE_AGE.
            self.request.session.set_expiry(0)
        return response


def logout_view(request):
    logout(request)
    return redirect("index")


def verify_email_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    valid = user is not None and email_verification_token.check_token(user, token)
    if valid and not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])

    return render(request, "accounts/verify_email_result.html", {"valid": valid})


@login_required
def resend_verification_view(request):
    if request.method == "POST" and not request.user.email_verified:
        _send_verification_email(request, request.user)
        messages.success(request, "Verification email sent — check your inbox.")
    return redirect("account_settings")


def _time_based_greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _compute_streak(user, today):
    """Consecutive days with a mood entry, counting back from today.
    If today's check-in isn't done yet, the streak still counts an
    unbroken run ending yesterday (so it doesn't reset at midnight
    before the person has had a chance to check in)."""
    day = today
    if not MoodEntry.objects.filter(user=user, date=day).exists():
        day -= timedelta(days=1)
    streak = 0
    while MoodEntry.objects.filter(user=user, date=day).exists():
        streak += 1
        day -= timedelta(days=1)
    return streak


@login_required
def dashboard_view(request):
    today = timezone.localdate()

    if request.method == "POST":
        form = MoodCheckInForm(request.POST)
        if form.is_valid():
            MoodEntry.objects.create(
                user=request.user,
                date=today,
                mood=form.cleaned_data["mood"],
                emotions=form.cleaned_data["emotions"],
                note=form.cleaned_data["note"],
            )
            # Redirect-after-POST: the GET that follows always builds a
            # fresh, blank form — nothing from the just-saved entry is
            # echoed back, since a new check-in should start clean.
            return redirect("dashboard")
    else:
        form = MoodCheckInForm()

    today_entries = list(
        MoodEntry.objects.filter(user=request.user, date=today).order_by("created_at")
    )

    # ── Last 7 days (oldest → newest) ────────────────────────
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    week_qs = MoodEntry.objects.filter(user=request.user, date__gte=days[0], date__lte=today)

    entries_by_day = {d: [] for d in days}
    for e in week_qs:
        entries_by_day.setdefault(e.date, []).append(e)

    chart_data = []
    for d in days:
        day_entries = entries_by_day.get(d, [])
        if day_entries:
            avg_for_day = sum(e.mood for e in day_entries) / len(day_entries)
            nearest_mood = round(avg_for_day)
        else:
            avg_for_day = None
            nearest_mood = 0
        chart_data.append(
            {
                "label": d.strftime("%a"),
                "is_today": d == today,
                "has_entry": bool(day_entries),
                "count": len(day_entries),
                "emoji": MoodEntry.MOOD_EMOJI.get(nearest_mood, ""),
                "height_pct": round(avg_for_day / 5 * 100) if avg_for_day else 4,
            }
        )

    all_week_entries = [e for entries in entries_by_day.values() for e in entries]

    freq = Counter(e.mood for e in all_week_entries)
    breakdown = [
        {
            "mood": level,
            "label": label,
            "emoji": MoodEntry.MOOD_EMOJI[level],
            "count": freq.get(level, 0),
        }
        for level, label in MoodEntry.MOOD_CHOICES
    ]
    max_breakdown_count = max((b["count"] for b in breakdown), default=0)

    avg_mood = None
    if all_week_entries:
        avg_mood = round(sum(e.mood for e in all_week_entries) / len(all_week_entries), 1)

    context = {
        "greeting": _time_based_greeting(),
        "form": form,
        "today_entries": today_entries,
        "mood_choices": MoodEntry.MOOD_CHOICES,
        "mood_emoji": MoodEntry.MOOD_EMOJI,
        "emotion_choices": MoodEntry.EMOTION_CHOICES,
        "chart_data": chart_data,
        "breakdown": breakdown,
        "max_breakdown_count": max_breakdown_count,
        "streak": _compute_streak(request.user, today),
        "avg_mood": avg_mood,
        "journal_count": JournalEntry.objects.filter(user=request.user).count(),
    }
    return render(request, "dashboard.html", context)


@login_required
def account_settings_view(request):
    if request.method == "POST" and "country" in request.POST:
        country = request.POST.get("country")
        if country in dict(User.COUNTRY_CHOICES):
            request.user.country = country
        request.user.weekly_insight_opt_in = bool(request.POST.get("weekly_insight_opt_in"))
        request.user.save(update_fields=["country", "weekly_insight_opt_in"])
        messages.success(request, "Preferences updated.")
        return redirect("account_settings")

    return render(request, "accounts/settings.html", {"delete_form": DeleteAccountForm()})


@login_required
def export_data_view(request):
    user = request.user
    data = {
        "profile": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "date_of_birth": str(user.date_of_birth) if user.date_of_birth else None,
            "phone": user.phone,
            "focus": user.focus,
            "country": user.country,
            "marketing_opt_in": user.marketing_opt_in,
            "date_joined": str(user.date_joined),
        },
        "mood_entries": [
            {
                "date": str(e.date),
                "mood": e.mood,
                "mood_label": e.get_mood_display(),
                "emotions": e.emotions,
                "note": e.note,
                "created_at": str(e.created_at),
            }
            for e in MoodEntry.objects.filter(user=user).order_by("date")
        ],
        "journal_entries": [
            {
                "content": j.content,
                "mood_tag": j.mood_tag,
                "created_at": str(j.created_at),
            }
            for j in JournalEntry.objects.filter(user=user).order_by("created_at")
        ],
    }

    try:
        from aichat.models import Conversation

        data["ai_chat_conversations"] = [
            {
                "started": str(c.created_at),
                "messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "has_image": bool(m.image),
                        "is_crisis_flagged": m.is_crisis,
                        "created_at": str(m.created_at),
                    }
                    for m in c.messages.order_by("created_at")
                ],
            }
            for c in Conversation.objects.filter(user=user).order_by("created_at")
        ]
    except Exception:
        data["ai_chat_conversations"] = []

    response = HttpResponse(json.dumps(data, indent=2), content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="mindspace-my-data.json"'
    return response


@login_required
def delete_account_view(request):
    if request.method == "POST":
        form = DeleteAccountForm(request.POST)
        if form.is_valid() and request.user.check_password(form.cleaned_data["password"]):
            user = request.user
            logout(request)
            user.delete()
            messages.success(request, "Your account and all associated data have been permanently deleted.")
            return redirect("index")
        messages.error(request, "Incorrect password — account was not deleted.")
    return redirect("account_settings")
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _compute_streak(user, today):
    """Consecutive days with a mood entry, counting back from today.
    If today's check-in isn't done yet, the streak still counts an
    unbroken run ending yesterday (so it doesn't reset at midnight
    before the person has had a chance to check in)."""
    day = today
    if not MoodEntry.objects.filter(user=user, date=day).exists():
        day -= timedelta(days=1)
    streak = 0
    while MoodEntry.objects.filter(user=user, date=day).exists():
        streak += 1
        day -= timedelta(days=1)
    return streak


@login_required
def dashboard_view(request):
    today = timezone.localdate()

    if request.method == "POST":
        form = MoodCheckInForm(request.POST)
        if form.is_valid():
            MoodEntry.objects.create(
                user=request.user,
                date=today,
                mood=form.cleaned_data["mood"],
                emotions=form.cleaned_data["emotions"],
                note=form.cleaned_data["note"],
            )
            # Redirect-after-POST: the GET that follows always builds a
            # fresh, blank form — nothing from the just-saved entry is
            # echoed back, since a new check-in should start clean.
            return redirect("dashboard")
    else:
        form = MoodCheckInForm()

    today_entries = list(
        MoodEntry.objects.filter(user=request.user, date=today).order_by("created_at")
    )

    # ── Last 7 days (oldest → newest) ────────────────────────
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    week_qs = MoodEntry.objects.filter(user=request.user, date__gte=days[0], date__lte=today)

    entries_by_day = {d: [] for d in days}
    for e in week_qs:
        entries_by_day.setdefault(e.date, []).append(e)

    chart_data = []
    for d in days:
        day_entries = entries_by_day.get(d, [])
        if day_entries:
            avg_for_day = sum(e.mood for e in day_entries) / len(day_entries)
            nearest_mood = round(avg_for_day)
        else:
            avg_for_day = None
            nearest_mood = 0
        chart_data.append(
            {
                "label": d.strftime("%a"),
                "is_today": d == today,
                "has_entry": bool(day_entries),
                "count": len(day_entries),
                "emoji": MoodEntry.MOOD_EMOJI.get(nearest_mood, ""),
                "height_pct": round(avg_for_day / 5 * 100) if avg_for_day else 4,
            }
        )

    all_week_entries = [e for entries in entries_by_day.values() for e in entries]

    freq = Counter(e.mood for e in all_week_entries)
    breakdown = [
        {
            "mood": level,
            "label": label,
            "emoji": MoodEntry.MOOD_EMOJI[level],
            "count": freq.get(level, 0),
        }
        for level, label in MoodEntry.MOOD_CHOICES
    ]
    max_breakdown_count = max((b["count"] for b in breakdown), default=0)

    avg_mood = None
    if all_week_entries:
        avg_mood = round(sum(e.mood for e in all_week_entries) / len(all_week_entries), 1)

    context = {
        "greeting": _time_based_greeting(),
        "form": form,
        "today_entries": today_entries,
        "mood_choices": MoodEntry.MOOD_CHOICES,
        "mood_emoji": MoodEntry.MOOD_EMOJI,
        "emotion_choices": MoodEntry.EMOTION_CHOICES,
        "chart_data": chart_data,
        "breakdown": breakdown,
        "max_breakdown_count": max_breakdown_count,
        "streak": _compute_streak(request.user, today),
        "avg_mood": avg_mood,
        "journal_count": JournalEntry.objects.filter(user=request.user).count(),
    }
    return render(request, "dashboard.html", context)
