"""
Matching clients to approved professionals.

Privacy: a client's location arrives in the request body (not the URL, so it
never lands in server logs), is rounded to ~1 km, used for this calculation
only, and never stored.
"""

import math

from .choices import SPECIALTIES
from .models import ProfessionalProfile

# Approximate city centres, used when a professional hasn't set an exact
# practice location. Distances from these are shown as approximate.
CITY_COORDS = {
    "pretoria": (-25.7479, 28.2293), "tshwane": (-25.7479, 28.2293), "centurion": (-25.8603, 28.1894),
    "johannesburg": (-26.2041, 28.0473), "joburg": (-26.2041, 28.0473), "sandton": (-26.1076, 28.0567),
    "soweto": (-26.2485, 27.8540), "midrand": (-25.9992, 28.1262), "randburg": (-26.0936, 28.0064),
    "roodepoort": (-26.1625, 27.8725), "benoni": (-26.1885, 28.3208), "boksburg": (-26.2125, 28.2625),
    "germiston": (-26.2178, 28.1672), "krugersdorp": (-26.0851, 27.7747), "vereeniging": (-26.6731, 27.9261),
    "cape town": (-33.9249, 18.4241), "stellenbosch": (-33.9321, 18.8602), "paarl": (-33.7342, 18.9621),
    "bellville": (-33.9003, 18.6290), "george": (-33.9630, 22.4617),
    "durban": (-29.8587, 31.0218), "pietermaritzburg": (-29.6006, 30.3794), "richards bay": (-28.7807, 32.0383),
    "umhlanga": (-29.7277, 31.0843), "newcastle": (-27.7580, 29.9318),
    "gqeberha": (-33.9608, 25.6022), "port elizabeth": (-33.9608, 25.6022), "east london": (-33.0153, 27.9116),
    "mthatha": (-31.5889, 28.7844), "makhanda": (-33.3106, 26.5256),
    "bloemfontein": (-29.0852, 26.1596), "welkom": (-27.9774, 26.7351),
    "polokwane": (-23.9045, 29.4689), "mbombela": (-25.4753, 30.9694), "nelspruit": (-25.4753, 30.9694),
    "emalahleni": (-25.8713, 29.2332), "witbank": (-25.8713, 29.2332),
    "kimberley": (-28.7282, 24.7499), "upington": (-28.4478, 21.2561),
    "rustenburg": (-25.6676, 27.2421), "mahikeng": (-25.8560, 25.6403), "potchefstroom": (-26.7145, 27.0970),
}

# What a client said brings them to MindSpace -> professional focus areas that fit.
REASON_TO_SPECIALTIES = {
    "anxiety_stress": ["anxiety_stress", "work"],
    "mood_tracking": ["low_mood", "general"],
    "habits": ["general", "work", "addiction"],
    "emotions": ["low_mood", "trauma", "grief", "relationships"],
    "therapy_support": [s for s, _ in SPECIALTIES],
    "general_wellness": ["general"],
    "other": ["general"],
    "prefer_not_to_say": [],
}
SPEC_LABEL = dict(SPECIALTIES)


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def pro_coords(p):
    if p.latitude is not None and p.longitude is not None:
        return (p.latitude, p.longitude), True
    c = CITY_COORDS.get((p.city or "").strip().lower())
    return (c, False) if c else (None, False)


def parse_point(lat, lng):
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return (round(lat, 2), round(lng, 2))  # ~1 km: enough for "near me", not a home address


def wanted_specialties(user, extra=None):
    reasons = list(getattr(user, "focus_reasons", None) or ([user.focus] if getattr(user, "focus", "") else []))
    wanted = []
    for r in reasons + list(extra or []):
        for s in REASON_TO_SPECIALTIES.get(r, [r] if r in SPEC_LABEL else []):
            if s not in wanted:
                wanted.append(s)
    return wanted


def public_card(p, distance_km=None, exact=True, matched=()):
    return {
        "id": p.pk,
        "display_name": p.display_name,
        "profession": p.profession,
        "profession_label": p.get_profession_display(),
        "regulator": p.regulator if p.regulator != "OTHER" else (p.regulator_other or "Other"),
        "registration_number": p.registration_number,
        "years_experience": p.years_experience,
        "city": p.city,
        "province": p.province,
        "offers_in_person": p.offers_in_person,
        "offers_online": p.offers_online,
        "fee_min": p.fee_min,
        "fee_max": p.fee_max,
        "accepts_medical_aid": p.accepts_medical_aid,
        "languages": p.languages,
        "specialties": [{"value": s, "label": SPEC_LABEL.get(s, s)} for s in p.specialties],
        "matched_specialties": [SPEC_LABEL.get(s, s) for s in matched],
        "distance_km": round(distance_km, 1) if distance_km is not None else None,
        "distance_is_approx": distance_km is not None and not exact,
    }


def public_profile(p):
    d = public_card(p)
    d.update(
        qualifications=p.qualifications,
        bio=p.bio,
        practice_name=p.practice_name,
        # street address only for in-person practices; phone only if they chose to share one
        address=p.address if p.offers_in_person else "",
        contact_phone=p.contact_phone,
    )
    return d


def match(user, *, point=None, mode="any", province=None, profession=None, language=None, extra_reasons=None, limit=20):
    """Returns (results, meta). mode: 'in_person' | 'online' | 'any'."""
    qs = ProfessionalProfile.objects.filter(status=ProfessionalProfile.APPROVED).select_related("user")
    if mode == "online":
        qs = qs.filter(offers_online=True)
    elif mode == "in_person":
        qs = qs.filter(offers_in_person=True)
    if profession:
        qs = qs.filter(profession=profession)
    if province and not point:
        qs = qs.filter(province=province)
    wanted = wanted_specialties(user, extra_reasons)

    scored = []
    for p in qs:
        if language and language not in (p.languages or []):
            continue
        matched = [s for s in wanted if s in (p.specialties or [])]
        coords, exact = pro_coords(p)
        dist = haversine_km(point, coords) if (point and coords) else None
        # Fit first, then (for in-person) closeness. Unknown distance sorts after known.
        fit = len(matched)
        near = dist if dist is not None else 10_000
        if mode == "online":
            near = 0
        scored.append((-fit, near, -p.years_experience, p.pk, public_card(p, dist, exact, matched)))
    scored.sort(key=lambda t: t[:4])
    results = [t[4] for t in scored[:limit]]
    return results, {"wanted_specialties": [SPEC_LABEL.get(s, s) for s in wanted], "used_location": bool(point)}
