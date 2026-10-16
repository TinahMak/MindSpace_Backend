"""Journal (uses the existing wellness.JournalEntry table) and safety plan endpoints."""

from collections import OrderedDict

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .content import JOURNAL_PROMPTS, RELATIONSHIPS, SAFETY_STEPS
from .models import SafetyPlan

MAX_JOURNAL = 10000


def _crisis_line(user):
    try:
        from api.views import _crisis_line_for

        return _crisis_line_for(user)
    except Exception:
        return None


def _is_crisis(text):
    try:
        from aichat.services import detect_crisis

        return bool(detect_crisis(text))
    except Exception:
        return False


@api_view(["GET"])
def selfcare_meta_view(request):
    return Response({
        "journal_prompts": [{"value": k, "label": l} for k, l in JOURNAL_PROMPTS],
        "safety_steps": SAFETY_STEPS,
        "relationships": RELATIONSHIPS,
    })


# ── journal ─────────────────────────────────────────────────────────────

def _entry(e):
    text = e.content or ""
    first = text.strip().split("\n", 1)[0]
    return {
        "id": e.pk,
        "content": text,
        "preview": first[:90] + ("…" if len(first) > 90 else ""),
        "mood": int(e.mood_tag) if str(e.mood_tag).isdigit() else None,
        "created_at": e.created_at,
    }


def _journal_input(request):
    content = str(request.data.get("content") or "").strip()
    if len(content) < 2:
        return None, None, Response({"detail": "Write a little before saving.", "content": ["Write a little before saving."]}, status=400)
    if len(content) > MAX_JOURNAL:
        return None, None, Response({"detail": "That entry is too long. Split it into two.", "content": ["Too long."]}, status=400)
    mood = request.data.get("mood")
    mood = str(mood) if str(mood) in {"1", "2", "3", "4", "5"} else ""
    return content, mood, None


@api_view(["GET", "POST"])
def journal_view(request):
    from wellness.models import JournalEntry

    if request.method == "POST":
        content, mood, err = _journal_input(request)
        if err:
            return err
        e = JournalEntry.objects.create(user=request.user, content=content, mood_tag=mood)
        data = _entry(e)
        if _is_crisis(content):
            data["crisis_line"] = _crisis_line(request.user)
        return Response(data, status=201)
    qs = JournalEntry.objects.filter(user=request.user).order_by("-created_at")
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(content__icontains=q)
    groups = OrderedDict()
    for e in qs[:300]:
        groups.setdefault(e.created_at.strftime("%B %Y"), []).append(_entry(e))
    return Response({"count": qs.count(), "groups": [{"month": m, "entries": v} for m, v in groups.items()]})


@api_view(["GET", "PATCH", "DELETE"])
def journal_entry_view(request, pk):
    from wellness.models import JournalEntry

    e = get_object_or_404(JournalEntry, pk=pk, user=request.user)
    if request.method == "DELETE":
        e.delete()
        return Response(status=204)
    if request.method == "PATCH":
        content, mood, err = _journal_input(request)
        if err:
            return err
        e.content, e.mood_tag = content, mood
        e.save()
        data = _entry(e)
        if _is_crisis(content):
            data["crisis_line"] = _crisis_line(request.user)
        return Response(data)
    return Response(_entry(e))


# ── safety plan ─────────────────────────────────────────────────────────

LIST_FIELDS = ("warning_signs", "coping", "distractions", "reasons")
CONTACT_FIELDS = ("people", "professionals")


def _plan_dict(p):
    d = {f: getattr(p, f) for f in LIST_FIELDS + CONTACT_FIELDS}
    d.update(safe_space=p.safe_space, updated_at=p.updated_at,
             trusted={"name": p.trusted_name, "relationship": p.trusted_relationship, "phone": p.trusted_phone} if p.trusted_phone else None)
    d["filled_steps"] = sum(1 for f in LIST_FIELDS + CONTACT_FIELDS if getattr(p, f))
    return d


@api_view(["GET", "PUT"])
def safety_plan_view(request):
    from api import validators as V

    plan, _ = SafetyPlan.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return Response(_plan_dict(plan))
    d = request.data
    country = getattr(request.user, "country", "ZA")
    for f in LIST_FIELDS:
        if f in d:
            items = [str(x).strip()[:120] for x in (d.get(f) or []) if str(x).strip()]
            setattr(plan, f, list(dict.fromkeys(items))[:15])
    for f in CONTACT_FIELDS:
        if f in d:
            out = []
            for c in (d.get(f) or [])[:8]:
                name = str(c.get("name") or "").strip()[:60]
                if not name:
                    continue
                try:
                    phone = V.clean_phone(c.get("phone"), country, required=False)
                except V.InputError as e:
                    return Response({"detail": f"{name}: {e}", f: [str(e)]}, status=400)
                out.append({"name": name, "phone": phone})
            setattr(plan, f, out)
    if "safe_space" in d:
        plan.safe_space = str(d.get("safe_space") or "").strip()[:1000]
    if "trusted" in d:
        t = d.get("trusted") or {}
        if not t or not str(t.get("phone") or "").strip():
            plan.trusted_name = plan.trusted_relationship = plan.trusted_phone = ""
        else:
            try:
                name = V.clean_name(t.get("name"), "Name")
                phone = V.clean_phone(t.get("phone"), country)
            except V.InputError as e:
                return Response({"detail": str(e), "trusted": [str(e)]}, status=400)
            plan.trusted_name, plan.trusted_phone = name, phone
            plan.trusted_relationship = t.get("relationship") if t.get("relationship") in RELATIONSHIPS else ""
    plan.save()
    return Response(_plan_dict(plan))
