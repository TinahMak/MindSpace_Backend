from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from . import validators as V

from aichat.models import Conversation, Message
from wellness.models import MoodEntry, WeeklyInsight

User = get_user_model()

MIN_AGE = 16
VALID_EMOTIONS = {key for key, _ in MoodEntry.EMOTION_CHOICES}

OTHER = "other"
EXCLUSIVE = "prefer_not_to_say"
_MODEL_FIELDS = {f.name for f in User._meta.get_fields()}
HAS_REASONS = {"focus_reasons", "focus_other"} <= _MODEL_FIELDS


def clean_reasons(reasons, other_text):
    """Validate a multi-select list of reasons (plus optional 'other' text).

    Returns (reasons, other_text, primary_focus). primary_focus is a single
    valid FOCUS_CHOICES value kept in the old `focus` field so the website's
    single-choice form keeps working."""
    valid = {k for k, _ in User.FOCUS_CHOICES} | {OTHER}
    if isinstance(reasons, str):
        reasons = [reasons]
    if not isinstance(reasons, list) or not reasons:
        raise serializers.ValidationError({"focus": "Choose at least one reason."})
    reasons = list(dict.fromkeys(str(r) for r in reasons))
    bad = [r for r in reasons if r not in valid]
    if bad:
        raise serializers.ValidationError({"focus": f"Unknown reason: {', '.join(bad)}"})
    if EXCLUSIVE in reasons and len(reasons) > 1:
        raise serializers.ValidationError({"focus": "\"Prefer not to say\" can't be combined with other reasons."})
    other_text = (other_text or "").strip()
    if OTHER in reasons:
        if len(other_text) < 2:
            raise serializers.ValidationError({"focus_other": "Tell us a little about your other reason."})
        if len(other_text) > 100:
            raise serializers.ValidationError({"focus_other": "Keep it under 100 characters."})
    else:
        other_text = ""
    primary = next((r for r in reasons if r != OTHER), "")
    return reasons, other_text, primary


def _age_on(dob, today):
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    def get_role(self, obj):
        # "admin", "professional" or "user": decides which area of the app opens.
        from professionals.services import role_of

        return role_of(obj)

    def get_is_admin(self, obj):
        return bool(obj.is_active and (obj.is_staff or obj.is_superuser))

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "date_of_birth",
            "phone",
            "focus",
            *(["focus_reasons", "focus_other"] if HAS_REASONS else []),
            "country",
            "weekly_insight_opt_in",
            "marketing_opt_in",
            "email_verified",
            "date_joined",
            "is_admin",
            "role",
        ]
        read_only_fields = ["id", "email", "email_verified", "date_joined", "date_of_birth", "focus"]

    def validate(self, attrs):
        # Phone is only re-checked when it's being changed (changing just the
        # country, e.g. for crisis lines, must not force a new number).
        if "phone" in attrs:
            country = attrs.get("country", getattr(self.instance, "country", "ZA"))
            try:
                attrs["phone"] = V.clean_phone(attrs["phone"], country, required=True)
            except V.InputError as e:
                raise serializers.ValidationError({"phone": str(e)})
        if HAS_REASONS and ("focus_reasons" in attrs or "focus_other" in attrs):
            reasons = attrs.get("focus_reasons", getattr(self.instance, "focus_reasons", []))
            other = attrs.get("focus_other", getattr(self.instance, "focus_other", ""))
            reasons, other, primary = clean_reasons(reasons, other)
            attrs.update(focus_reasons=reasons, focus_other=other, focus=primary)
        return attrs

    def validate_country(self, value):
        if value not in dict(User.COUNTRY_CHOICES):
            raise serializers.ValidationError("Choose a country from the list.")
        return value

    def validate_first_name(self, value):
        return _run(V.clean_name, value, "First name")

    def validate_last_name(self, value):
        return _run(V.clean_name, value, "Last name")



def _run(fn, *args):
    try:
        return fn(*args)
    except V.InputError as e:
        raise serializers.ValidationError(str(e))


class SignupSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    date_of_birth = serializers.DateField()
    password = serializers.CharField(write_only=True, min_length=8)
    focus = serializers.JSONField()  # a list of reasons (a single string also works)
    focus_other = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30)
    country = serializers.ChoiceField(choices=User.COUNTRY_CHOICES, required=False, default="ZA")
    marketing_opt_in = serializers.BooleanField(required=False, default=False)
    terms_accepted = serializers.BooleanField()
    age_confirmed = serializers.BooleanField()

    def validate_first_name(self, value):
        return _run(V.clean_name, value, "First name")

    def validate_last_name(self, value):
        return _run(V.clean_name, value, "Last name")

    def validate_email(self, value):
        value = _run(V.clean_email, value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists. Log in instead.")
        return value

    def validate_date_of_birth(self, value):
        return _run(V.clean_dob, value)

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError("You must agree to the Terms of Service and Privacy Policy.")
        return value

    def validate_age_confirmed(self, value):
        if not value:
            raise serializers.ValidationError(f"You must confirm you are {MIN_AGE} or older.")
        return value

    def validate(self, attrs):
        try:
            attrs["phone"] = V.clean_phone(attrs.get("phone"), attrs.get("country", "ZA"), required=True)
        except V.InputError as e:
            raise serializers.ValidationError({"phone": str(e)})
        reasons, other, primary = clean_reasons(attrs.get("focus"), attrs.get("focus_other"))
        attrs["focus_reasons"], attrs["focus_other"], attrs["focus"] = reasons, other, primary
        return attrs

    def create(self, data):
        user = User(
            username=data["email"],
            email=data["email"],
            first_name=data["first_name"].strip(),
            last_name=data["last_name"].strip(),
            date_of_birth=data["date_of_birth"],
            focus=data["focus"],
            **({"focus_reasons": data["focus_reasons"], "focus_other": data["focus_other"]} if HAS_REASONS else {}),
            phone=data["phone"],
            country=data.get("country", "ZA"),
            marketing_opt_in=data.get("marketing_opt_in", False),
            terms_accepted_at=timezone.now(),
        )
        user.set_password(data["password"])
        user.save()
        return user


class MoodEntrySerializer(serializers.ModelSerializer):
    emoji = serializers.CharField(read_only=True)
    label = serializers.CharField(source="get_mood_display", read_only=True)

    class Meta:
        model = MoodEntry
        fields = ["id", "date", "mood", "label", "emoji", "emotions", "note", "created_at"]
        read_only_fields = ["id", "date", "created_at"]

    def validate_emotions(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Emotions must be a list.")
        bad = [v for v in value if v not in VALID_EMOTIONS]
        if bad:
            raise serializers.ValidationError(f"Unknown emotion tag: {', '.join(map(str, bad))}")
        return list(dict.fromkeys(value))

    def validate_note(self, value):
        return (value or "").strip()[:500]


class MessageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    suggested_mood_emoji = serializers.SerializerMethodField()
    suggested_mood_label = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "role",
            "content",
            "image_url",
            "is_crisis",
            "suggested_mood",
            "suggested_mood_emoji",
            "suggested_mood_label",
            "suggested_emotions",
            "created_at",
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url

    def get_suggested_mood_emoji(self, obj):
        return MoodEntry.MOOD_EMOJI.get(obj.suggested_mood) if obj.suggested_mood else None

    def get_suggested_mood_label(self, obj):
        return dict(MoodEntry.MOOD_CHOICES).get(obj.suggested_mood) if obj.suggested_mood else None


class ConversationSerializer(serializers.ModelSerializer):
    preview = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ["id", "created_at", "updated_at", "preview", "message_count"]

    def get_preview(self, obj):
        first = obj.messages.filter(role="user").order_by("created_at").first()
        if not first:
            return "New conversation"
        text = (first.content or "").strip() or "Shared a photo"
        return text[:80]

    def get_message_count(self, obj):
        return obj.messages.count()


class WeeklyInsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyInsight
        fields = [
            "id",
            "period_start",
            "period_end",
            "total_entries",
            "avg_mood",
            "concern_level",
            "summary_text",
            "emailed_at",
            "created_at",
        ]
