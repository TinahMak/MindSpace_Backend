"""
Admin rules, shared by the web panel and the mobile API so both behave
identically.

Privacy rule: admins manage ACCOUNTS. Nothing here returns mood entries,
notes, journal text or chat messages; only counts.
"""

from collections import Counter
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import AdminAction, AppRating

User = get_user_model()


class AdminError(Exception):
    """A rule was broken; the message is safe to show the admin."""


def is_admin(user):
    return bool(user and user.is_authenticated and user.is_active and (user.is_staff or user.is_superuser))


def log(actor, action, target=None, detail=""):
    AdminAction.objects.create(
        actor=actor,
        actor_email=actor.email,
        action=action,
        target_email=getattr(target, "email", "") or "",
        detail=detail[:255],
    )


def _guard(actor, target, verb):
    if target.pk == actor.pk:
        raise AdminError(f"You can't {verb} your own account here.")
    if target.is_superuser and not actor.is_superuser:
        raise AdminError(f"Only the owner account can {verb} another owner account.")


# ── users ───────────────────────────────────────────────────────────────

def search_users(q="", status="all", limit=50, offset=0):
    qs = User.objects.all().order_by("-date_joined")
    q = (q or "").strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "suspended":
        qs = qs.filter(is_active=False)
    elif status == "admins":
        qs = qs.filter(Q(is_staff=True) | Q(is_superuser=True))
    return qs.count(), list(qs[offset : offset + limit])


def user_summary(u):
    return {
        "id": u.pk,
        "email": u.email,
        "name": f"{u.first_name} {u.last_name}".strip(),
        "is_active": u.is_active,
        "is_admin": bool(u.is_staff or u.is_superuser),
        "is_owner": u.is_superuser,
        "email_verified": getattr(u, "email_verified", False),
        "date_joined": u.date_joined,
        "last_login": u.last_login,
    }


def user_detail(u):
    """Account facts and activity COUNTS only, never the content."""
    from aichat.models import Conversation, Message
    from wellness.models import MoodEntry

    week_ago = timezone.localdate() - timedelta(days=6)
    rating = AppRating.objects.filter(user=u).first()
    data = user_summary(u)
    data.update(
        country=getattr(u, "country", ""),
        mood_entries=MoodEntry.objects.filter(user=u).count(),
        mood_entries_7d=MoodEntry.objects.filter(user=u, date__gte=week_ago).count(),
        conversations=Conversation.objects.filter(user=u).count(),
        messages=Message.objects.filter(conversation__user=u, role="user").count(),
        rating={"stars": rating.stars, "comment": rating.comment} if rating else None,
    )
    return data


def suspend_user(actor, target):
    _guard(actor, target, "suspend")
    if not target.is_active:
        raise AdminError("This account is already suspended.")
    target.is_active = False
    target.save(update_fields=["is_active"])
    try:  # sign them out of the mobile app immediately
        from rest_framework.authtoken.models import Token

        Token.objects.filter(user=target).delete()
    except Exception:
        pass
    log(actor, "suspend", target)


def reactivate_user(actor, target):
    if target.is_active:
        raise AdminError("This account is already active.")
    target.is_active = True
    target.save(update_fields=["is_active"])
    log(actor, "reactivate", target)


def delete_user(actor, target, confirm_email):
    _guard(actor, target, "delete")
    if (confirm_email or "").strip().lower() != target.email.lower():
        raise AdminError("Type the user's email address exactly to confirm deletion.")
    email = target.email
    log(actor, "delete", target, "Account and all its data permanently deleted")
    target.delete()
    return email


# ── admins ──────────────────────────────────────────────────────────────

def list_admins():
    return list(User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).order_by("date_joined"))


def add_admin(actor, email):
    email = (email or "").strip().lower()
    target = User.objects.filter(email__iexact=email).first()
    if not target:
        raise AdminError("No MindSpace account uses that email. Ask them to sign up first, then add them.")
    if not target.is_active:
        raise AdminError("That account is suspended. Reactivate it first.")
    if target.is_staff or target.is_superuser:
        raise AdminError("That person is already an admin.")
    target.is_staff = True
    target.save(update_fields=["is_staff"])
    log(actor, "add_admin", target)
    return target


def remove_admin(actor, target):
    _guard(actor, target, "remove admin rights from")
    if not (target.is_staff or target.is_superuser):
        raise AdminError("That person isn't an admin.")
    if target.is_superuser:
        raise AdminError("The owner account can't be removed here. Use the Django admin if you really need to.")
    target.is_staff = False
    target.save(update_fields=["is_staff"])
    log(actor, "remove_admin", target)


# ── ratings & dashboard ─────────────────────────────────────────────────

def ratings_summary(weeks=8):
    qs = AppRating.objects.all()
    agg = qs.aggregate(avg=Avg("stars"), n=Count("id"))
    dist = Counter(qs.values_list("stars", flat=True))
    today = timezone.localdate()
    trend = []
    for i in range(weeks - 1, -1, -1):
        start = today - timedelta(days=today.weekday() + 7 * i)
        end = start + timedelta(days=7)
        w = qs.filter(updated_at__date__gte=start, updated_at__date__lt=end).aggregate(avg=Avg("stars"), n=Count("id"))
        trend.append({"week_start": start, "avg": round(w["avg"], 2) if w["avg"] else None, "count": w["n"]})
    return {
        "average": round(agg["avg"], 2) if agg["avg"] else None,
        "count": agg["n"],
        "distribution": [{"stars": s, "count": dist.get(s, 0)} for s in range(5, 0, -1)],
        "trend": trend,
    }


def recent_ratings(limit=30, only_with_comments=False):
    qs = AppRating.objects.select_related("user")
    if only_with_comments:
        qs = qs.exclude(comment="")
    return [
        {
            "stars": r.stars,
            "comment": r.comment,
            "platform": r.platform,
            "email": r.user.email if r.user else "deleted user",
            "updated_at": r.updated_at,
        }
        for r in qs[:limit]
    ]


def dashboard_stats():
    from wellness.models import MoodEntry

    now = timezone.now()
    week_ago = timezone.localdate() - timedelta(days=6)
    r = ratings_summary(weeks=1)
    return {
        "users_total": User.objects.count(),
        "users_new_7d": User.objects.filter(date_joined__gte=now - timedelta(days=7)).count(),
        "users_active_7d": MoodEntry.objects.filter(date__gte=week_ago).values("user").distinct().count(),
        "users_suspended": User.objects.filter(is_active=False).count(),
        "admins": User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).count(),
        "rating_average": r["average"],
        "rating_count": r["count"],
        "pros_pending": _pros_count("pending"),
        "pros_approved": _pros_count("approved"),
        **_consult_counts(),
    }


def _consult_counts():
    """Counts only: admins never see the content of consultation requests."""
    try:
        from professionals.consultations import counts

        c = counts()
        return {"consults_open": c["requested"] + c["quoted"], "consults_accepted": c["accepted"]}
    except Exception:
        return {"consults_open": 0, "consults_accepted": 0}


def _pros_count(status):
    try:
        from professionals.models import ProfessionalProfile

        return ProfessionalProfile.objects.filter(status=status).count()
    except Exception:  # professionals app not installed yet
        return 0


def audit_log(limit=100):
    return [
        {
            "actor": a.actor_email,
            "action": a.action,
            "target": a.target_email,
            "detail": a.detail,
            "created_at": a.created_at,
        }
        for a in AdminAction.objects.all()[:limit]
    ]
