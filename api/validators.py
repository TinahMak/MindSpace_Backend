"""
Shared input rules for names, emails, phone numbers, dates of birth and
session times. Used by every signup and profile form, so the website API,
the app and the admin tools all enforce the same thing.
"""

import re
from datetime import date, datetime, timedelta

from django.utils import timezone

MIN_AGE = 16  # MindSpace's minimum age (see Terms). Never lower than 12.
MAX_AGE = 120

# local@domain.tld : letters/digits in domain labels, a real dot-separated TLD of 2+ letters.
EMAIL_RE = re.compile(
    r"^(?=.{6,254}$)[A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9])?"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$"
)
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$", re.UNICODE)

COUNTRY_TO_REGION = {"ZA": "ZA", "US": "US", "GB": "GB", "CA": "CA", "AU": "AU", "IN": "IN"}


class InputError(ValueError):
    pass


# ── email domain checks ────────────────────────────────────────────────
# A syntactically valid address can still be clearly wrong ("name@g.com",
# "name@gmial.com", "name@gmail.con"). These rules catch the common mistakes
# and suggest the fix. The same rules live in the mobile app (src/lib/validate.js)
# and the website signup page, so all three agree.

# Big providers and the only domains they actually use.
PROVIDERS = {
    "gmail": {"gmail.com"},
    "hotmail": {"hotmail.com", "hotmail.co.uk", "hotmail.co.za", "hotmail.fr", "hotmail.de", "hotmail.it", "hotmail.es"},
    "outlook": {"outlook.com", "outlook.co.za", "outlook.co.uk", "outlook.fr", "outlook.de", "outlook.es"},
    "icloud": {"icloud.com"},
    "yahoo": {"yahoo.com", "yahoo.co.za", "yahoo.co.uk", "yahoo.fr", "yahoo.de", "yahoo.es", "yahoo.it", "yahoo.ca", "yahoo.in", "yahoo.com.au"},
}
# Real domains that look a lot like a provider's name; never "correct" these.
LOOKALIKES_OK = {
    "mail.com", "email.com", "googlemail.com", "gmx.com", "gmx.net", "ymail.com", "aol.com", "msn.com", "live.com", "me.com", "mac.com",
    "proton.me", "protonmail.com", "zoho.com", "outlook.office365.com",
    "webmail.co.za", "mweb.co.za", "telkomsa.net", "vodamail.co.za", "absamail.co.za", "iafrica.com",
}
# Endings that are almost always a slip of the finger for ".com".
TLD_TYPOS = {"con", "cmo", "cpm", "vom", "xom", "ocm", "comm", "coom", "cim", "clm"}
SECOND_LEVEL = {"co", "ac", "org", "gov", "net", "edu", "com", "mil", "nom", "web"}


def _edit_distance(a, b):
    """Typos needed to turn a into b. Swapped neighbours ("gmial") count as one."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _suggest(name, domain):
    """Keep the person's own ending when the provider uses it (yaho.co.za -> yahoo.co.za)."""
    ending = domain.split(".", 1)[1] if "." in domain else "com"
    guess = f"{name}.{ending}"
    return guess if guess in PROVIDERS[name] else f"{name}.com"


def _main_label(domain):
    """'mail.uct.ac.za' -> 'uct', 'gmail.com' -> 'gmail'."""
    labels = domain.split(".")
    if len(labels) >= 3 and labels[-2] in SECOND_LEVEL and len(labels[-1]) == 2:
        return labels[-3]
    return labels[-2]


def email_domain_problem(email):
    """Returns a friendly message if the domain is clearly a mistake, else None."""
    local, _, domain = email.partition("@")
    if domain in LOOKALIKES_OK:
        return None
    label = _main_label(domain)
    tld = domain.rsplit(".", 1)[-1]

    # 1. The provider's name is right but the ending is wrong: gmail.con, gmail.co, hotmail.cm
    if label in PROVIDERS and domain not in PROVIDERS[label]:
        return f"Did you mean {local}@{_suggest(label, domain)}?"

    # 2. A misspelt or shortened provider name: gmial.com, gmal.com, g.com, yaho.com, outlok.com
    for name in PROVIDERS:
        close = _edit_distance(label, name) <= (1 if len(name) <= 5 else 2)
        shortened = len(label) < len(name) and name.startswith(label) and len(label) <= 3
        if label != name and (close or shortened):
            return f"Did you mean {local}@{_suggest(name, domain)}?"

    # 3. ".con" and friends
    if tld in TLD_TYPOS:
        return f"Did you mean {local}@{domain[: -len(tld)]}com?"

    # 4. A one-letter domain name ("name@x.com") is almost never a real mailbox.
    if len(label) < 2:
        return "That email domain doesn't look right. Check the part after the @."
    return None


def clean_email(value):
    v = (value or "").strip().lower()
    if not EMAIL_RE.match(v) or ".." in v or v.split("@")[1].startswith("-"):
        raise InputError("Enter a valid email address, like name@example.com.")
    problem = email_domain_problem(v)
    if problem:
        raise InputError(problem)
    return v


def clean_name(value, label="Name"):
    v = re.sub(r"\s+", " ", (value or "").strip())
    if len(v) < 2:
        raise InputError(f"{label} must be at least 2 characters.")
    if len(v) > 60:
        raise InputError(f"{label} is too long.")
    if not NAME_RE.match(v):
        raise InputError(f"{label} can only contain letters, spaces, hyphens and apostrophes.")
    return v


def clean_phone(value, country="ZA", required=True):
    """Returns the number in international format (+27...), or '' if optional and empty."""
    import phonenumbers

    raw = (value or "").strip()
    if not raw:
        if required:
            raise InputError("Enter your phone number.")
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7 or len(set(digits.lstrip("0") or "0")) <= 1:
        raise InputError("That phone number isn't valid.")
    if digits in "01234567890123456789" or digits in "98765432109876543210":
        raise InputError("That phone number isn't valid.")
    region = COUNTRY_TO_REGION.get((country or "").upper())
    if not region and not raw.startswith("+"):
        raise InputError("Enter your number in international format, starting with + and your country code.")
    try:
        num = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        raise InputError("That phone number isn't valid.")
    if not phonenumbers.is_valid_number(num):
        where = {"ZA": "South African", "US": "US", "GB": "UK", "CA": "Canadian", "AU": "Australian", "IN": "Indian"}.get(region)
        raise InputError(f"That isn't a valid {where} phone number." if where else "That phone number isn't valid.")
    if region and phonenumbers.region_code_for_number(num) != region:
        raise InputError("That number doesn't match the country you chose.")
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def age_on(dob, today=None):
    today = today or timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def clean_dob(value, min_age=MIN_AGE):
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            raise InputError("Enter a valid date of birth.")
    if value > timezone.localdate():
        raise InputError("Date of birth can't be in the future.")
    a = age_on(value)
    if a < min_age:
        raise InputError(f"You must be at least {min_age} years old to use MindSpace.")
    if a > MAX_AGE:
        raise InputError("Please check your date of birth.")
    return value


def clean_future_slot(value, min_lead_minutes=60):
    """A session time must be a real date-time at least an hour from now."""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise InputError("Pick each session time with the date and time picker.")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    if dt < timezone.now() + timedelta(minutes=min_lead_minutes):
        raise InputError("Session times must be at least an hour from now.")
    if dt > timezone.now() + timedelta(days=180):
        raise InputError("Session times must be within the next 6 months.")
    return dt.isoformat()
