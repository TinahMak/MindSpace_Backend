"""
Rules for professional onboarding, shared by the mobile API and the web panel.

Verification is done by a human admin: the app records the registration
number and documents, and the admin checks them against the HPCSA or
SACSSP public register before approving.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .choices import DEFAULT_REGULATOR, LANGUAGES, PROFESSIONS, PROVINCES, REGULATORS, SPECIALTIES, TITLES
from .models import ProfessionalDocument, ProfessionalProfile

User = get_user_model()

ALLOWED_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
MAX_DOC_BYTES = 10 * 1024 * 1024
MAX_DOCS = 8
# Changing these sends an approved profile back to review.
REVIEWED_FIELDS = ("profession", "regulator", "regulator_other", "registration_number")


class ProError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def role_of(user):
    if not (user and user.is_authenticated):
        return "anonymous"
    if user.is_staff or user.is_superuser:
        return "admin"
    if hasattr(user, "professional"):
        return "professional"
    return "user"


def clean_profile(data, partial=False):
    """Validate profile fields from a form or JSON. Returns a dict of clean values."""
    out = {}

    def has(k):
        return k in data and data[k] is not None

    def text(k, maxlen, required=False, label=None):
        if has(k) or not partial:
            v = str(data.get(k) or "").strip()
            if required and not v:
                raise ProError(f"{label or k.replace('_', ' ').capitalize()} is required.", k)
            out[k] = v[:maxlen]

    if has("profession") or not partial:
        p = data.get("profession")
        if p not in dict(PROFESSIONS):
            raise ProError("Choose your profession.", "profession")
        out["profession"] = p
    if has("regulator") or not partial:
        r = data.get("regulator") or DEFAULT_REGULATOR.get(out.get("profession"), "")
        if r not in dict(REGULATORS):
            raise ProError("Choose the body you're registered with.", "regulator")
        out["regulator"] = r
    if out.get("regulator") == "OTHER" or (partial and has("regulator_other")):
        text("regulator_other", 100, required=out.get("regulator") == "OTHER", label="Name of your professional body")
    elif "regulator" in out:
        out["regulator_other"] = ""

    if has("title") or not partial:
        t = str(data.get("title") or "").strip()
        if t and t not in TITLES:
            raise ProError("Choose a title from the list.", "title")
        out["title"] = t
    text("registration_number", 40, required=True, label="Registration number")
    text("qualifications", 1000, required=True, label="Qualifications")
    text("bio", 1500)
    text("practice_name", 120)
    text("address", 200)
    text("city", 80, required=True, label="City or town")
    if has("contact_phone") or not partial:
        from api import validators as V

        try:
            out["contact_phone"] = V.clean_phone(data.get("contact_phone"), "ZA", required=False)
        except V.InputError as e:
            raise ProError(str(e), "contact_phone")
    if has("province") or not partial:
        if data.get("province") not in PROVINCES:
            raise ProError("Choose your province.", "province")
        out["province"] = data["province"]

    if has("years_experience") or not partial:
        try:
            y = int(data.get("years_experience") or 0)
        except (TypeError, ValueError):
            raise ProError("Years of experience must be a number.", "years_experience")
        if not 0 <= y <= 70:
            raise ProError("Years of experience looks wrong.", "years_experience")
        out["years_experience"] = y

    for k, allowed, label in (("specialties", dict(SPECIALTIES), "focus area"), ("languages", LANGUAGES, "language")):
        if has(k) or not partial:
            v = data.get(k) or []
            if isinstance(v, str):
                v = [x for x in v.split(",") if x]
            v = list(dict.fromkeys(v))
            bad = [x for x in v if x not in allowed]
            if bad:
                raise ProError(f"Unknown {label}: {', '.join(bad)}", k)
            out[k] = v
    if not partial and not out["specialties"]:
        raise ProError("Choose at least one focus area.", "specialties")
    if not partial and not out["languages"]:
        raise ProError("Choose at least one language.", "languages")

    for k in ("offers_in_person", "offers_online", "accepts_medical_aid"):
        if has(k):
            out[k] = str(data[k]).lower() in ("1", "true", "on", "yes")
    if not partial and not (out.get("offers_in_person", True) or out.get("offers_online")):
        raise ProError("Offer in-person sessions, online sessions, or both.", "offers_online")

    for k in ("fee_min", "fee_max"):
        if has(k) or not partial:
            raw = data.get(k)
            if raw in (None, ""):
                out[k] = None
            else:
                try:
                    out[k] = int(raw)
                except (TypeError, ValueError):
                    raise ProError("Fees must be whole numbers in rand.", k)
                if not 0 <= out[k] <= 100000:
                    raise ProError("That fee looks wrong.", k)
    if "latitude" in data or "longitude" in data:
        lat, lng = data.get("latitude"), data.get("longitude")
        if lat in (None, "") and lng in (None, ""):
            out["latitude"] = out["longitude"] = None
        else:
            try:
                lat, lng = float(lat), float(lng)
            except (TypeError, ValueError):
                raise ProError("That location isn't valid.", "latitude")
            if not (-35.5 <= lat <= -21.5 and 16 <= lng <= 33.5):
                raise ProError("The practice location must be in South Africa.", "latitude")
            out["latitude"], out["longitude"] = round(lat, 5), round(lng, 5)
    lo, hi = out.get("fee_min"), out.get("fee_max")
    if lo is not None and hi is not None and hi < lo:
        raise ProError("The maximum fee can't be lower than the minimum.", "fee_max")
    return out


@transaction.atomic
def create_professional(*, email, first_name, last_name, password=None, profile_data, admin=None):
    from api import validators as V

    try:
        email = V.clean_email(email)
    except V.InputError as e:
        raise ProError(str(e), "email")
    try:
        first_name = V.clean_name(first_name, "First name")
    except V.InputError as e:
        raise ProError(str(e), "first_name")
    try:
        last_name = V.clean_name(last_name, "Last name")
    except V.InputError as e:
        raise ProError(str(e), "last_name")
    if User.objects.filter(email__iexact=email).exists():
        raise ProError("An account with this email already exists.", "email")
    clean = clean_profile(profile_data)
    user = User(username=email, email=email, first_name=first_name.strip()[:150], last_name=last_name.strip()[:150])
    if password:
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        try:
            validate_password(password, user)
        except ValidationError as e:
            raise ProError(" ".join(e.messages), "password")
        user.set_password(password)
    else:
        # Admin-created: a random password nobody knows; they choose their own via the emailed link.
        import secrets

        user.set_password(secrets.token_urlsafe(32))
    if hasattr(user, "terms_accepted_at"):
        user.terms_accepted_at = timezone.now()
    user.save()
    profile = ProfessionalProfile.objects.create(user=user, created_by_admin=bool(admin), **clean)
    if admin:
        profile.status = ProfessionalProfile.APPROVED
        profile.reviewed_by = admin
        profile.reviewed_at = timezone.now()
        profile.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        _log(admin, "add_professional", user, profile.get_profession_display())
    return profile


def update_own_profile(profile, data):
    clean = clean_profile(data, partial=True)
    needs_review = profile.status == ProfessionalProfile.APPROVED and any(
        k in clean and clean[k] != getattr(profile, k) for k in REVIEWED_FIELDS
    )
    for k, v in clean.items():
        setattr(profile, k, v)
    if needs_review:
        profile.status = ProfessionalProfile.PENDING
        profile.status_reason = "Registration details changed, so your profile is being reviewed again."
    profile.save()
    return profile, needs_review


def resubmit(profile):
    if profile.status != ProfessionalProfile.REJECTED:
        raise ProError("Only a rejected application can be resubmitted.")
    if not profile.documents.exists():
        raise ProError("Upload at least one document before resubmitting.")
    profile.status = ProfessionalProfile.PENDING
    profile.save(update_fields=["status", "updated_at"])


def add_document(profile, uploaded, kind):
    if profile.status == ProfessionalProfile.SUSPENDED:
        raise ProError("Your profile is suspended. Contact MindSpace support.")
    if profile.documents.count() >= MAX_DOCS:
        raise ProError(f"You can upload up to {MAX_DOCS} documents. Remove one first.")
    if kind not in dict(ProfessionalDocument._meta.get_field("kind").choices):
        kind = "other"
    ctype = (uploaded.content_type or "").lower()
    if ctype == "image/jpg":
        ctype = "image/jpeg"
    if ctype not in ALLOWED_TYPES:
        raise ProError("Upload a PDF, JPG or PNG file.")
    if uploaded.size > MAX_DOC_BYTES:
        raise ProError("That file is larger than 10 MB.")
    head = uploaded.read(8)
    uploaded.seek(0)
    magic_ok = (
        (ctype == "application/pdf" and head.startswith(b"%PDF"))
        or (ctype == "image/jpeg" and head.startswith(b"\xff\xd8"))
        or (ctype == "image/png" and head.startswith(b"\x89PNG"))
    )
    if not magic_ok:
        raise ProError("That file doesn't look like a real PDF, JPG or PNG.")
    return ProfessionalDocument.objects.create(
        profile=profile,
        kind=kind,
        file=uploaded,
        original_name=(uploaded.name or "document")[:200],
        content_type=ctype,
        size=uploaded.size,
    )


def delete_document(profile, doc):
    if profile.status == ProfessionalProfile.APPROVED:
        raise ProError("Approved profiles can't remove documents. Contact support if one needs replacing.")
    doc.delete()


# ── admin decisions ─────────────────────────────────────────────────────

def _log(admin, action, target_user, detail=""):
    from adminpanel.services import log

    log(admin, action, target_user, detail)


def _notify(profile, subject, body):
    try:
        send_mail(subject, body, None, [profile.user.email], fail_silently=True)
    except Exception:
        pass


def decide(admin, profile, action, reason=""):
    S = ProfessionalProfile
    reason = (reason or "").strip()[:500]
    if profile.user_id == admin.pk:
        raise ProError("You can't review your own professional profile.")
    if action == "approve":
        if profile.status == S.APPROVED:
            raise ProError("Already approved.")
        if not profile.created_by_admin and not profile.documents.exists():
            raise ProError("This professional hasn't uploaded any documents yet, so they can't be verified.")
        profile.status, profile.status_reason = S.APPROVED, ""
        _notify(profile, "Your MindSpace profile is approved",
                f"Hi {profile.user.first_name},\n\nGood news: your MindSpace professional profile has been approved.\n\nThe MindSpace team")
    elif action == "reject":
        if len(reason) < 5:
            raise ProError("Give a short reason so the professional knows what to fix.", "reason")
        profile.status, profile.status_reason = S.REJECTED, reason
        _notify(profile, "Your MindSpace application needs changes",
                f"Hi {profile.user.first_name},\n\nWe couldn't approve your MindSpace profile yet:\n\n{reason}\n\n"
                "You can update your details or documents in the app and resubmit.\n\nThe MindSpace team")
    elif action == "suspend":
        if profile.status == S.SUSPENDED:
            raise ProError("Already suspended.")
        if len(reason) < 5:
            raise ProError("Give a short reason for the suspension.", "reason")
        profile.status, profile.status_reason = S.SUSPENDED, reason
    elif action == "reinstate":
        if profile.status != S.SUSPENDED:
            raise ProError("Only suspended profiles can be reinstated.")
        profile.status, profile.status_reason = S.APPROVED, ""
    else:
        raise ProError("Unknown action.")
    profile.reviewed_by, profile.reviewed_at = admin, timezone.now()
    profile.save()
    _log(admin, f"pro_{action}", profile.user, reason or profile.get_profession_display())
    return profile


def send_set_password_email(request, user):
    """Emails the website's standard 'set a new password' link. If that page
    isn't available, falls back to a plain welcome email pointing them to
    'Forgot password'."""
    form = PasswordResetForm({"email": user.email})
    if form.is_valid():
        try:
            form.save(request=request, use_https=request.is_secure())
            return True
        except Exception:
            pass
    try:
        send_mail(
            "You've been added to MindSpace",
            f"Hi {user.first_name},\n\nA MindSpace admin has added your professional profile.\n\n"
            "To get started, open the MindSpace app, tap Log in, then 'Forgot password?', and enter this "
            "email address to choose your own password.\n\nThe MindSpace team",
            None,
            [user.email],
        )
        return True
    except Exception:
        return False


def meta():
    return {
        "professions": [
            {"value": v, "label": l, "default_regulator": DEFAULT_REGULATOR.get(v)} for v, l in PROFESSIONS
        ],
        "regulators": [{"value": v, "label": l} for v, l in REGULATORS],
        "specialties": [{"value": v, "label": l} for v, l in SPECIALTIES],
        "languages": LANGUAGES,
        "provinces": PROVINCES,
        "titles": TITLES,
        "doc_kinds": [{"value": v, "label": l} for v, l in ProfessionalDocument._meta.get_field("kind").choices],
        "max_doc_mb": MAX_DOC_BYTES // (1024 * 1024),
    }


def profile_dict(p, request=None, include_docs=True):
    d = {
        "id": p.pk,
        "user_id": p.user_id,
        "email": p.user.email,
        "first_name": p.user.first_name,
        "last_name": p.user.last_name,
        "display_name": p.display_name,
        "profession_label": p.get_profession_display(),
        "regulator_label": p.get_regulator_display() if p.regulator != "OTHER" else p.regulator_other,
        "status_label": p.get_status_display(),
    }
    for f in (
        "title", "profession", "regulator", "regulator_other", "registration_number", "qualifications",
        "years_experience", "bio", "specialties", "languages", "practice_name", "address", "city", "province",
        "offers_in_person", "offers_online", "fee_min", "fee_max", "accepts_medical_aid", "contact_phone",
        "status", "status_reason", "created_by_admin", "reviewed_at", "created_at", "latitude", "longitude",
    ):
        d[f] = getattr(p, f)
    if include_docs:
        d["documents"] = [
            {
                "id": doc.pk,
                "kind": doc.kind,
                "kind_label": doc.get_kind_display(),
                "name": doc.original_name,
                "content_type": doc.content_type,
                "size": doc.size,
                "uploaded_at": doc.uploaded_at,
            }
            for doc in p.documents.all()
        ]
    return d
