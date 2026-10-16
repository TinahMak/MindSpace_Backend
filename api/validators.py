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


def clean_email(value):
    v = (value or "").strip().lower()
    if not EMAIL_RE.match(v) or ".." in v or v.split("@")[1].startswith("-"):
        raise InputError("Enter a valid email address, like name@example.com.")
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
