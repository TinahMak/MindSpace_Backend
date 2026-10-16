"""
Consultation requests and quotes.

Privacy: until the client accepts a quote, the professional sees only the
client's first name plus what the client chose to share. Name, email (and
phone if shared) are revealed on acceptance. Admins see counts only.
"""

from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .choices import SPECIALTIES
from .models import ConsultationRequest as CR
from .models import ProfessionalProfile

SPEC_LABEL = dict(SPECIALTIES)
MAX_OPEN_PER_CLIENT = 5
DURATIONS = (30, 45, 50, 60, 90)
VALID_DAYS = (3, 7, 14)


class ConsultError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def _mail(to, subject, body):
    try:
        send_mail(subject, body, None, [to], fail_silently=True)
    except Exception:
        pass


def expire_if_needed(r):
    if r.status == CR.QUOTED and r.valid_until and r.valid_until < timezone.localdate():
        r.status = CR.EXPIRED
        r.save(update_fields=["status", "updated_at"])
    return r


def mood_summary_for(user):
    """Numbers only. Never notes or chat content."""
    try:
        from wellness.services import analyze_mood_patterns

        s = analyze_mood_patterns(user, days=14)
    except Exception:
        return ""
    if not s.get("total_entries"):
        return "No mood check-ins in the last 14 days."
    parts = [f"{s['total_entries']} check-ins in the last 14 days", f"average mood {s['avg_mood']} out of 5"]
    if s.get("trend"):
        parts.append(f"trend: {s['trend']}")
    if s.get("low_ratio") is not None:
        parts.append(f"{round(s['low_ratio'] * 100)}% of check-ins low or very low")
    if s.get("top_emotions"):
        parts.append("most common feelings: " + ", ".join(s["top_emotions"]))
    return "; ".join(parts) + "."


# ── client actions ──────────────────────────────────────────────────────

@transaction.atomic
def create_request(client, professional_id, data):
    from professionals.services import role_of

    if role_of(client) != "user":
        raise ConsultError("Only client accounts can request consultations.")
    pro = ProfessionalProfile.objects.filter(pk=professional_id, status=ProfessionalProfile.APPROVED).first()
    if not pro:
        raise ConsultError("This professional isn't available right now.")
    if CR.objects.filter(client=client, professional=pro, status__in=CR.OPEN).exists():
        raise ConsultError("You already have an open request with this professional.")
    if CR.objects.filter(client=client, status__in=CR.OPEN).count() >= MAX_OPEN_PER_CLIENT:
        raise ConsultError(f"You can have up to {MAX_OPEN_PER_CLIENT} open requests. Cancel one first.")

    mode = data.get("mode") or "either"
    if mode not in dict(CR.MODES):
        raise ConsultError("Choose in person, online or either.", "mode")
    if mode == "online" and not pro.offers_online:
        raise ConsultError("This professional doesn't offer online sessions.", "mode")
    if mode == "in_person" and not pro.offers_in_person:
        raise ConsultError("This professional only offers online sessions.", "mode")
    topics = [t for t in dict.fromkeys(data.get("topics") or []) if t in SPEC_LABEL]
    message = str(data.get("message") or "").strip()[:1000]
    if not topics and len(message) < 5:
        raise ConsultError("Choose what you'd like help with, or write a short message.", "topics")
    phone = ""
    if data.get("share_phone"):
        from api import validators as V

        try:
            phone = V.clean_phone(data.get("phone") or getattr(client, "phone", ""), getattr(client, "country", "ZA"))
        except V.InputError as e:
            raise ConsultError(str(e), "phone")

    r = CR.objects.create(
        client=client,
        professional=pro,
        mode=mode,
        topics=topics,
        message=message,
        preferred_times=str(data.get("preferred_times") or "").strip()[:200],
        mood_summary=mood_summary_for(client) if data.get("share_mood_summary") else "",
        phone=phone,
    )
    _mail(pro.user.email, "New consultation request on MindSpace",
          f"Hi {pro.user.first_name},\n\nYou have a new consultation request from {client.first_name or 'a MindSpace user'}. "
          "Open the Requests tab in the MindSpace app to send a quote.\n\nThe MindSpace team")
    return r


def _own(client, pk):
    r = CR.objects.select_related("professional__user").filter(pk=pk, client=client).first()
    if not r:
        raise ConsultError("Request not found.")
    return expire_if_needed(r)


def accept(client, pk, slot_index):
    r = _own(client, pk)
    if r.status == CR.EXPIRED:
        raise ConsultError("This quote has expired. You can send a new request.")
    if r.status != CR.QUOTED:
        raise ConsultError("There's no quote to accept yet.")
    try:
        slot = r.slots[int(slot_index)] if r.slots else ""
    except (ValueError, TypeError, IndexError):
        raise ConsultError("Choose one of the offered times.", "slot")
    from datetime import datetime

    try:
        if datetime.fromisoformat(slot) <= timezone.now():
            raise ConsultError("That time has already passed. Choose another, or ask for a new quote.", "slot")
    except ValueError:
        pass  # older free-text times
    r.status, r.chosen_slot, r.decided_at = CR.ACCEPTED, slot, timezone.now()
    r.save()
    c = r.client
    contact = f"{c.first_name} {c.last_name}".strip() + f", {c.email}" + (f", {r.phone}" if r.phone else "")
    _mail(r.professional.user.email, "Your MindSpace quote was accepted",
          f"Hi {r.professional.user.first_name},\n\n{c.first_name} accepted your quote"
          + (f" for {slot}" if slot else "") + f".\n\nContact: {contact}\n\nPlease get in touch to confirm.\n\nThe MindSpace team")
    return r


def decline(client, pk, reason=""):
    r = _own(client, pk)
    if r.status != CR.QUOTED:
        raise ConsultError("Only a quote can be declined.")
    r.status, r.response_note, r.decided_at = CR.DECLINED_BY_CLIENT, str(reason or "").strip()[:500], timezone.now()
    r.save()
    return r


def cancel(client, pk):
    r = _own(client, pk)
    if r.status not in CR.OPEN:
        raise ConsultError("This request is already closed.")
    r.status, r.decided_at = CR.CANCELLED, timezone.now()
    r.save()
    return r


# ── professional actions ────────────────────────────────────────────────

def _for_pro(pro_user, pk):
    r = CR.objects.select_related("client", "professional").filter(pk=pk, professional__user=pro_user).first()
    if not r:
        raise ConsultError("Request not found.")
    return expire_if_needed(r)


def _require_approved(pro_user):
    p = getattr(pro_user, "professional", None)
    if not p or p.status != ProfessionalProfile.APPROVED:
        raise ConsultError("Only approved professionals can respond to requests.")


def quote(pro_user, pk, data):
    _require_approved(pro_user)
    r = _for_pro(pro_user, pk)
    if r.status not in (CR.REQUESTED, CR.QUOTED):
        raise ConsultError("This request is closed.")
    try:
        fee = int(data.get("fee"))
    except (TypeError, ValueError):
        raise ConsultError("Enter your fee in rand.", "fee")
    if not 0 <= fee <= 100000:
        raise ConsultError("That fee looks wrong.", "fee")
    try:
        duration = int(data.get("duration_min"))
    except (TypeError, ValueError):
        duration = 0
    if duration not in DURATIONS:
        raise ConsultError("Choose a session length.", "duration_min")
    mode = data.get("quote_mode") or ""
    allowed = [m for m, ok in (("in_person", r.professional.offers_in_person), ("online", r.professional.offers_online)) if ok]
    if mode not in allowed:
        raise ConsultError("Choose in person or online.", "quote_mode")
    from api import validators as V

    raw = [s for s in (data.get("slots") or []) if str(s).strip()][:3]
    if not raw:
        raise ConsultError("Offer at least one time.", "slots")
    try:
        slots = sorted(dict.fromkeys(V.clean_future_slot(s) for s in raw))
    except V.InputError as e:
        raise ConsultError(str(e), "slots")
    try:
        days = int(data.get("valid_days") or 7)
    except (TypeError, ValueError):
        days = 7
    if days not in VALID_DAYS:
        days = 7
    r.fee, r.duration_min, r.quote_mode, r.slots = fee, duration, mode, slots
    r.quote_note = str(data.get("quote_note") or "").strip()[:1000]
    r.valid_until = timezone.localdate() + timedelta(days=days)
    r.status, r.quoted_at = CR.QUOTED, timezone.now()
    r.save()
    _mail(r.client.email, "You have a quote on MindSpace",
          f"Hi {r.client.first_name},\n\n{r.professional.display_name} sent you a quote of R{fee} for a {duration}-minute session. "
          "Open MindSpace to accept or decline it.\n\nThe MindSpace team")
    return r


def pro_decline(pro_user, pk, reason):
    r = _for_pro(pro_user, pk)
    if r.status not in (CR.REQUESTED, CR.QUOTED):
        raise ConsultError("This request is closed.")
    reason = str(reason or "").strip()
    if len(reason) < 5:
        raise ConsultError("Give the client a short reason, for example that you're fully booked.", "reason")
    r.status, r.response_note, r.decided_at = CR.DECLINED_BY_PRO, reason[:500], timezone.now()
    r.save()
    _mail(r.client.email, "Update on your MindSpace request",
          f"Hi {r.client.first_name},\n\n{r.professional.display_name} can't take your request right now:\n\n{reason}\n\n"
          "You can find other professionals in the Support tab.\n\nThe MindSpace team")
    return r


# ── serialisation (what each side may see) ──────────────────────────────

def to_dict(r, viewer):
    expire_if_needed(r)
    p = r.professional
    d = {
        "id": r.pk,
        "status": r.status,
        "status_label": r.get_status_display(),
        "mode": r.mode,
        "mode_label": r.get_mode_display(),
        "topics": [{"value": t, "label": SPEC_LABEL.get(t, t)} for t in r.topics],
        "message": r.message,
        "preferred_times": r.preferred_times,
        "mood_summary": r.mood_summary,
        "shared_phone": bool(r.phone),
        "quote": None,
        "chosen_slot": r.chosen_slot,
        "response_note": r.response_note,
        "created_at": r.created_at,
        "quoted_at": r.quoted_at,
        "decided_at": r.decided_at,
    }
    if r.fee is not None:
        d["quote"] = {
            "fee": r.fee,
            "duration_min": r.duration_min,
            "mode": r.quote_mode,
            "mode_label": dict(CR.MODES).get(r.quote_mode, r.quote_mode),
            "slots": r.slots,
            "note": r.quote_note,
            "valid_until": r.valid_until,
        }
    if viewer == "client":
        d["professional"] = {
            "id": p.pk,
            "display_name": p.display_name,
            "profession_label": p.get_profession_display(),
            "city": p.city,
            "contact_phone": p.contact_phone if r.status == CR.ACCEPTED else "",
            "email": p.user.email if r.status == CR.ACCEPTED else "",
            "address": p.address if (r.status == CR.ACCEPTED and r.quote_mode == "in_person") else "",
        }
    else:  # professional
        c = r.client
        revealed = r.status == CR.ACCEPTED
        d["client"] = {
            "first_name": c.first_name or "MindSpace user",
            "full_name": f"{c.first_name} {c.last_name}".strip() if revealed else "",
            "email": c.email if revealed else "",
            "phone": r.phone if revealed else "",
            "revealed": revealed,
        }
    return d


def counts():
    from django.db.models import Count

    rows = dict(CR.objects.values_list("status").annotate(n=Count("id")))
    return {s: rows.get(s, 0) for s, _ in CR.STATUS_CHOICES}
