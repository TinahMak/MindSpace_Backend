"""
MindSpace mobile API (v10).

Every endpoint reuses the same models and service functions as the website,
so the Expo app and the web app share one Supabase database and one set of
rules. Safety behaviour is carried over unchanged:

* Crisis-language detection is the same deterministic detect_crisis() used
  on the web, runs BEFORE the AI call, and is never rate-limited.
* Crisis line data comes from core.crisis_lines (verified numbers).
* Wellness data only leaves the app when the person exports it themselves.
"""

import logging
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from aichat.models import Conversation, Message
from wellness.models import JournalEntry, MoodEntry, WeeklyInsight

from .serializers import (
    ConversationSerializer,
    MessageSerializer,
    MoodEntrySerializer,
    SignupSerializer,
    UserSerializer,
    WeeklyInsightSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()

VALID_PERIODS = (7, 14, 30)
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class AuthRateThrottle(AnonRateThrottle):
    """Slows down password guessing on login and reset. Only applied to
    auth endpoints; nothing in chat or crisis handling is throttled."""

    rate = "20/min"


# ── helpers ─────────────────────────────────────────────────────────────

def _clean_days(request, default=14):
    try:
        days = int(request.query_params.get("days", default))
    except (TypeError, ValueError):
        days = default
    return days if days in VALID_PERIODS else default


def _auth_payload(user, request):
    token, _ = Token.objects.get_or_create(user=user)
    return {"token": token.key, "user": UserSerializer(user, context={"request": request}).data}


def _site_base(request):
    """Links in emails point at the website. SITE_URL in .env wins; otherwise
    we fall back to the host the request came in on."""
    base = getattr(settings, "SITE_URL", "") or ""
    return base.rstrip("/") if base else request.build_absolute_uri("/").rstrip("/")


def _send_verification_email(user, request):
    from accounts.tokens import email_verification_token

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    link = f"{_site_base(request)}/accounts/verify-email/{uid}/{token}/"
    name = f" {user.first_name}" if user.first_name else ""
    body = (
        f"Hi{name},\n\n"
        "Welcome to MindSpace. Please confirm your email address by opening this link:\n\n"
        f"{link}\n\n"
        "If you didn't create a MindSpace account, you can ignore this email."
    )
    try:
        send_mail("Confirm your MindSpace email", body, None, [user.email], fail_silently=False)
        return True
    except Exception:
        logger.exception("Could not send verification email to %s", user.email)
        return False


def _compute_streak(user, today):
    """Use the website's own streak rule when available so both apps agree."""
    try:
        from accounts.views import _compute_streak as web_streak

        return web_streak(user, today)
    except Exception:
        dates = set(MoodEntry.objects.filter(user=user).values_list("date", flat=True))
        streak, day = 0, today
        if day not in dates:
            day -= timedelta(days=1)
        while day in dates:
            streak += 1
            day -= timedelta(days=1)
        return streak


def _greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _crisis_line_for(user):
    from core.crisis_lines import CRISIS_LINES, DEFAULT_COUNTRY

    code = getattr(user, "country", None)
    if code not in CRISIS_LINES:
        code = DEFAULT_COUNTRY
    return {"country": code, **CRISIS_LINES[code]}


# ── meta ────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def meta_view(request):
    """Choice lists the app needs for forms, served from the models so the
    two apps can never drift apart."""
    return Response(
        {
            "moods": [
                {"value": v, "label": l, "emoji": MoodEntry.MOOD_EMOJI[v]} for v, l in MoodEntry.MOOD_CHOICES
            ],
            "emotions": [{"value": v, "label": l} for v, l in MoodEntry.EMOTION_CHOICES],
            "focus_choices": [{"value": v, "label": l} for v, l in User.FOCUS_CHOICES]
            + [{"value": "other", "label": "Other"}],
            "countries": [{"value": v, "label": l} for v, l in User.COUNTRY_CHOICES],
            "insight_periods": list(VALID_PERIODS),
            "min_age": 16,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def health_view(request):
    return Response({"ok": True, "service": "mindspace-api", "version": "v10"})


# ── auth ────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def signup_view(request):
    serializer = SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        user = serializer.save()
    sent = _send_verification_email(user, request)
    payload = _auth_payload(user, request)
    payload["verification_email_sent"] = sent
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def login_view(request):
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password") or ""
    if not email or not password:
        return Response({"detail": "Enter your email and password."}, status=400)
    from .validators import EMAIL_RE

    if not EMAIL_RE.match(email):
        return Response({"detail": "Enter a valid email address, like name@example.com."}, status=400)
    user = authenticate(request, email=email, password=password)
    if user is None:
        # Some backends authenticate on the username kwarg even with a custom USERNAME_FIELD.
        user = authenticate(request, username=email, password=password)
    if user is None or not user.is_active:
        return Response({"detail": "Invalid email or password. Please try again."}, status=400)
    return Response(_auth_payload(user, request))


@api_view(["POST"])
def logout_view(request):
    Token.objects.filter(user=request.user).delete()
    return Response({"detail": "Logged out."})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def password_reset_view(request):
    """Sends the same password-reset email as the website. Always answers
    the same way so the endpoint can't be used to check which emails exist."""
    form = PasswordResetForm({"email": (request.data.get("email") or "").strip()})
    if form.is_valid():
        try:
            base = _site_base(request)
            form.save(
                request=request,
                use_https=base.startswith("https"),
                domain_override=base.split("://", 1)[-1],
            )
        except Exception:
            logger.exception("Password reset email failed")
    return Response({"detail": "If an account exists for that email, a reset link is on its way."})


@api_view(["POST"])
def resend_verification_view(request):
    if request.user.email_verified:
        return Response({"detail": "Your email is already verified."})
    sent = _send_verification_email(request.user, request)
    if not sent:
        return Response({"detail": "We couldn't send the email right now. Try again shortly."}, status=503)
    return Response({"detail": f"Verification email sent to {request.user.email}."})


# ── account ─────────────────────────────────────────────────────────────

@api_view(["GET", "PATCH"])
def me_view(request):
    if request.method == "GET":
        return Response(UserSerializer(request.user, context={"request": request}).data)
    serializer = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["GET"])
def export_view(request):
    """Everything MindSpace stores about the person, as JSON (same scope as
    the website's Export my data)."""
    user = request.user
    conversations = []
    for conv in Conversation.objects.filter(user=user).order_by("created_at"):
        conversations.append(
            {
                "id": conv.id,
                "created_at": conv.created_at,
                "messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "had_image": bool(m.image),
                        "is_crisis": m.is_crisis,
                        "created_at": m.created_at,
                    }
                    for m in conv.messages.order_by("created_at")
                ],
            }
        )
    data = {
        "exported_at": timezone.now(),
        "profile": UserSerializer(user, context={"request": request}).data,
        "mood_entries": MoodEntrySerializer(MoodEntry.objects.filter(user=user).order_by("created_at"), many=True).data,
        "journal_entries": [
            {"content": j.content, "mood_tag": j.mood_tag, "created_at": j.created_at}
            for j in JournalEntry.objects.filter(user=user).order_by("created_at")
        ],
        "weekly_insights": WeeklyInsightSerializer(WeeklyInsight.objects.filter(user=user), many=True).data,
        "safety_plan": _safety_plan_export(user),
        "conversations": conversations,
    }
    return Response(data)


@api_view(["POST"])
def delete_account_view(request):
    password = request.data.get("password") or ""
    if not request.user.check_password(password):
        return Response({"detail": "Incorrect password. Your account was not deleted."}, status=400)
    request.user.delete()  # cascades to moods, chats, insights, journal, token
    return Response({"detail": "Your account and all its data have been deleted."})


# ── mood tracking ───────────────────────────────────────────────────────

@api_view(["GET", "POST"])
def moods_view(request):
    if request.method == "POST":
        serializer = MoodEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(user=request.user)
        return Response(MoodEntrySerializer(entry).data, status=201)

    qs = MoodEntry.objects.filter(user=request.user)
    day = request.query_params.get("date")
    if day:
        qs = qs.filter(date=day)
    try:
        limit = min(int(request.query_params.get("limit", 50)), 200)
    except ValueError:
        limit = 50
    return Response(MoodEntrySerializer(qs.order_by("-created_at")[:limit], many=True).data)


@api_view(["DELETE"])
def mood_detail_view(request, pk):
    entry = get_object_or_404(MoodEntry, pk=pk, user=request.user)
    entry.delete()
    return Response(status=204)


@api_view(["GET"])
def dashboard_view(request):
    """Same numbers as the web dashboard: today's check-ins, 7-day chart,
    mood frequency breakdown, streak, weekly average, journal count."""
    user = request.user
    today = timezone.localdate()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    week = list(MoodEntry.objects.filter(user=user, date__gte=days[0], date__lte=today))

    by_day = {d: [] for d in days}
    for e in week:
        by_day.setdefault(e.date, []).append(e)

    chart = []
    for d in days:
        items = by_day.get(d, [])
        avg = sum(e.mood for e in items) / len(items) if items else None
        chart.append(
            {
                "date": d.isoformat(),
                "label": d.strftime("%a"),
                "is_today": d == today,
                "count": len(items),
                "avg": round(avg, 2) if avg is not None else None,
                "emoji": MoodEntry.MOOD_EMOJI.get(round(avg), "") if avg else "",
            }
        )

    freq = Counter(e.mood for e in week)
    breakdown = [
        {"mood": v, "label": l, "emoji": MoodEntry.MOOD_EMOJI[v], "count": freq.get(v, 0)}
        for v, l in MoodEntry.MOOD_CHOICES
    ]
    avg_mood = round(sum(e.mood for e in week) / len(week), 1) if week else None
    low_days = len({e.date for e in week if e.mood <= 2})
    suggest_support = low_days >= 3 or (len(week) >= 3 and avg_mood is not None and avg_mood <= 2.2)
    today_entries = sorted(by_day.get(today, []), key=lambda e: e.created_at)

    return Response(
        {
            "greeting": _greeting(),
            "first_name": user.first_name,
            "email_verified": user.email_verified,
            "today_entries": MoodEntrySerializer(today_entries, many=True).data,
            "chart": chart,
            "breakdown": breakdown,
            "streak": _compute_streak(user, today),
            "avg_mood": avg_mood,
            "week_count": len(week),
            "journal_count": JournalEntry.objects.filter(user=user).count(),
            "suggest_support": suggest_support,
            "low_days_7d": low_days,
        }
    )


# ── insights & reports ──────────────────────────────────────────────────

@api_view(["GET"])
def insights_view(request):
    from wellness.services import analyze_mood_patterns

    days = _clean_days(request)
    stats = analyze_mood_patterns(request.user, days=days)
    stats["top_emotions_labeled"] = [
        {"value": t, "label": dict(MoodEntry.EMOTION_CHOICES).get(t, t)} for t in stats.get("top_emotions", [])
    ]
    return Response({"days": days, "periods": list(VALID_PERIODS), "stats": stats})


@api_view(["GET"])
def report_pdf_view(request):
    from wellness.report import build_mood_report_pdf

    days = _clean_days(request)
    pdf = build_mood_report_pdf(request.user, days=days)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="mindspace-mood-report-{days}days.pdf"'
    return response


@api_view(["GET"])
def weekly_insights_view(request):
    qs = WeeklyInsight.objects.filter(user=request.user)[:12]
    return Response(WeeklyInsightSerializer(qs, many=True).data)


@api_view(["POST"])
def weekly_generate_view(request):
    """Same synchronous 'Generate now' path as the website: no Celery or
    Redis needed."""
    from wellness.tasks import _generate_for_user

    insight = _generate_for_user(request.user)
    return Response(WeeklyInsightSerializer(insight).data, status=201)


# ── AI chat companion ───────────────────────────────────────────────────

@api_view(["GET", "POST"])
def conversations_view(request):
    if request.method == "POST":
        conv = Conversation.objects.create(user=request.user)
        return Response(ConversationSerializer(conv).data, status=201)
    qs = Conversation.objects.filter(user=request.user).order_by("-updated_at")[:50]
    return Response(ConversationSerializer(qs, many=True).data)


@api_view(["GET"])
def current_conversation_view(request):
    """The most recent conversation, created if the person has none (same
    rule as the web chat page)."""
    conv = Conversation.objects.filter(user=request.user).order_by("-updated_at").first()
    if conv is None:
        conv = Conversation.objects.create(user=request.user)
    return _conversation_payload(conv, request)


def _conversation_payload(conv, request):
    msgs = conv.messages.order_by("created_at")
    has_crisis = msgs.filter(is_crisis=True).exists()
    return Response(
        {
            "conversation": ConversationSerializer(conv).data,
            "messages": MessageSerializer(msgs, many=True, context={"request": request}).data,
            "show_crisis_banner": has_crisis,
            "crisis_line": _crisis_line_for(request.user),
        }
    )


@api_view(["GET", "DELETE"])
def conversation_detail_view(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, user=request.user)
    if request.method == "DELETE":
        conv.delete()
        return Response(status=204)
    return _conversation_payload(conv, request)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def send_message_view(request, pk):
    """Send a message (optionally with a photo) and get the AI reply.

    Order matters and matches the web app: crisis detection runs first and
    the user's message is saved before the AI is called, so a failed AI call
    never loses what the person wrote and never hides the crisis banner."""
    from aichat.services import detect_crisis, get_ai_reply, get_mood_suggestion

    conv = get_object_or_404(Conversation, pk=pk, user=request.user)
    content = (request.data.get("content") or "").strip()
    image = request.FILES.get("image")

    if not content and not image:
        return Response({"detail": "Type a message or add a photo."}, status=400)
    if len(content) > 4000:
        return Response({"detail": "That message is too long. Keep it under 4000 characters."}, status=400)
    if image:
        if image.size > MAX_IMAGE_BYTES:
            return Response({"detail": "That photo is too large. Choose one under 8 MB."}, status=400)
        if not (image.content_type or "").startswith("image/"):
            return Response({"detail": "Only photos can be attached."}, status=400)

    is_crisis = detect_crisis(content)
    user_msg = Message.objects.create(
        conversation=conv, role="user", content=content, image=image, is_crisis=is_crisis
    )
    conv.save(update_fields=["updated_at"])

    assistant_msg = None
    ai_error = None
    try:
        reply = get_ai_reply(conv)
        assistant_msg = Message.objects.create(conversation=conv, role="assistant", content=reply)
        if user_msg.image:
            suggestion = get_mood_suggestion(user_msg)
            if suggestion:
                assistant_msg.suggested_mood = suggestion.get("mood")
                assistant_msg.suggested_emotions = suggestion.get("emotions") or []
                assistant_msg.save(update_fields=["suggested_mood", "suggested_emotions"])
    except Exception:
        logger.exception("AI reply failed for conversation %s", conv.pk)
        ai_error = "Couldn't reach the AI companion just now. Your message was saved, so try again in a moment."

    from .support_signals import support_signal

    signal = support_signal(content, is_crisis)
    ctx = {"request": request}
    return Response(
        {
            "support_signal": signal,
            "user_message": MessageSerializer(user_msg, context=ctx).data,
            "assistant_message": MessageSerializer(assistant_msg, context=ctx).data if assistant_msg else None,
            "ai_error": ai_error,
            "is_crisis": is_crisis,
            "show_crisis_banner": is_crisis or conv.messages.filter(is_crisis=True).exists(),
            "crisis_line": _crisis_line_for(request.user),
        },
        status=201,
    )


@api_view(["POST"])
def log_suggested_mood_view(request, pk):
    """One-tap: log the mood the AI suggested from a photo."""
    msg = get_object_or_404(Message, pk=pk, conversation__user=request.user, role="assistant")
    if not msg.suggested_mood:
        return Response({"detail": "This message has no mood suggestion."}, status=400)
    entry = MoodEntry.objects.create(
        user=request.user,
        mood=msg.suggested_mood,
        emotions=list(msg.suggested_emotions or []),
        note="Logged from a photo in AI chat",
    )
    return Response(MoodEntrySerializer(entry).data, status=201)


# ── get help ────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def help_view(request):
    """Verified crisis lines. Public on purpose: this must work even when
    someone is logged out or their session has expired."""
    from core.crisis_lines import CRISIS_LINES, DEFAULT_COUNTRY, FALLBACK_DIRECTORY_URL

    try:
        from core.crisis_lines import THERAPIST_DIRECTORIES
    except ImportError:
        THERAPIST_DIRECTORIES = []

    country = request.query_params.get("country")
    if country not in CRISIS_LINES:
        user_country = getattr(request.user, "country", None) if request.user.is_authenticated else None
        country = user_country if user_country in CRISIS_LINES else DEFAULT_COUNTRY

    labels = dict(User.COUNTRY_CHOICES)
    return Response(
        {
            "selected_country": country,
            "line": {"country": country, **CRISIS_LINES[country]},
            "lines": [{"country": c, "country_label": labels.get(c, c), **d} for c, d in CRISIS_LINES.items()],
            "fallback_directory_url": FALLBACK_DIRECTORY_URL,
            "therapist_directories": THERAPIST_DIRECTORIES,
            "emergency_note": "If you are in immediate danger, call your local emergency number now.",
            "trusted_contact": _trusted_contact(request.user),
            "has_safety_plan": _has_safety_plan(request.user),
        }
    )


def _trusted_contact(user):
    if not user.is_authenticated:
        return None
    try:
        p = user.safety_plan
    except Exception:
        return None
    return {"name": p.trusted_name, "relationship": p.trusted_relationship, "phone": p.trusted_phone} if p.trusted_phone else None


def _has_safety_plan(user):
    if not user.is_authenticated:
        return False
    try:
        p = user.safety_plan
    except Exception:
        return False
    return any([p.warning_signs, p.coping, p.distractions, p.people, p.professionals, p.reasons])



def _safety_plan_export(user):
    try:
        from selfcare.api import _plan_dict

        return _plan_dict(user.safety_plan)
    except Exception:
        return None
