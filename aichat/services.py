"""
AI chat backend logic: crisis-language detection (deterministic, keyword
based — this does NOT rely on the model to decide whether to show the
helpline banner), the conversational Gemini call, and a separate structured
call that turns a shared photo into a loggable mood suggestion.
"""
import logging

from django.conf import settings
from google import genai
from google.genai import types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Deterministic, pattern-level trigger list — intentionally not exhaustive.
# This exists to reliably surface the helpline banner; it is not a
# substitute for the model's own judgement, which still shapes the
# actual reply via the system prompt below.
CRISIS_PHRASES = [
    "suicide", "suicidal",
    "kill myself", "end my life", "end it all",
    "want to die", "wish i was dead", "wish i were dead",
    "no reason to live", "not worth living", "better off dead",
    "self harm", "self-harm", "selfharm",
    "hurt myself", "hurting myself", "harm myself",
    "cutting myself", "cut myself",
    "can't go on", "cant go on", "can't do this anymore", "cant do this anymore",
    "take my own life",
]

SOUTH_AFRICA_CRISIS_LINE = "0800 567 567"

SYSTEM_PROMPT = """You are the AI companion inside MindSpace, a mental wellness app. \
You are warm, empathetic, and non-judgmental — like a caring, emotionally intelligent \
friend who happens to be a good listener.

Guidelines:
- Respond with warmth and genuine curiosity about how the person is doing. Keep replies \
conversational and not overly long.
- You are not a therapist and cannot diagnose conditions. Never claim to know what \
mental health condition someone has. If asked directly, gently clarify you're a \
wellness companion, not a clinician, and suggest professional support for anything \
that sounds like it needs it.
- If the person shares something indicating they may be in crisis (thoughts of suicide, \
self-harm, or being unable to cope), respond with care, take it seriously, gently \
encourage them to reach out to a crisis line or trusted person right now, and do not \
try to talk them out of it yourself or provide any information that could be used for \
self-harm. The app will also show them a crisis helpline banner automatically.
- If the person shares a photo of themselves, you may make ONE gentle, tentative \
observation about what their expression or body language seems to convey (e.g. "you \
look like you might be tired today") as a small caring notice — never a diagnosis, \
never stated as fact, and always followed by asking how they're actually feeling in \
their own words. If the photo isn't a personal photo (e.g. a pet, a meme, a landscape), \
just engage with it naturally without forcing a mood reading.
- Keep every reply to a few sentences unless the person is clearly asking for something \
longer (like a breathing exercise script or a longer reflection).
"""


def detect_crisis(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(phrase in lowered for phrase in CRISIS_PHRASES)


def _build_user_parts(message):
    """Build a list of google.genai Part objects for one stored Message,
    including the image bytes inline if the message has an attached photo."""
    parts = []
    if message.image:
        try:
            message.image.open("rb")
            raw = message.image.read()
            message.image.close()
            media_type = "image/jpeg"
            name = message.image.name.lower()
            if name.endswith(".png"):
                media_type = "image/png"
            elif name.endswith(".webp"):
                media_type = "image/webp"
            elif name.endswith(".gif"):
                media_type = "image/gif"
            parts.append(types.Part.from_bytes(data=raw, mime_type=media_type))
        except Exception:
            logger.exception("Failed to read chat image for message %s", message.pk)
    if message.content:
        parts.append(types.Part.from_text(text=message.content))
    elif not parts:
        parts.append(types.Part.from_text(text="(shared a photo)"))
    return parts


def get_ai_reply(conversation):
    """Call the Gemini API with the conversation's full history and return
    the assistant's reply text. Raises on failure — the caller decides how
    to surface that to the user."""
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to your .env file to enable AI chat."
        )

    client = genai.Client(api_key=api_key)

    contents = []
    for msg in conversation.messages.order_by("created_at"):
        if msg.role == "user":
            contents.append(types.Content(role="user", parts=_build_user_parts(msg)))
        else:
            contents.append(
                types.Content(role="model", parts=[types.Part.from_text(text=msg.content)])
            )

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=600,
        ),
    )

    return (response.text or "").strip()


class _MoodSuggestion(BaseModel):
    mood: int
    emotions: list[str]
    is_personal_photo: bool


def get_mood_suggestion(message):
    """Given a user Message with an attached photo, ask Gemini for a
    structured, tentative mood-level (1-5) + emotion-tag suggestion the
    person can review and choose to log. Returns None if the photo doesn't
    look personal, the call fails, or no API key is configured — the chat
    itself never breaks because of this, it just won't offer the button."""
    from wellness.models import MoodEntry

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key or not message.image:
        return None

    valid_tags = ", ".join(key for key, _ in MoodEntry.EMOTION_CHOICES)
    instruction = (
        "Look at the attached photo together with any accompanying text. "
        "If it looks like a personal photo showing the person's own face or "
        "body language, give a tentative, gentle read of their mood: a mood "
        "level from 1 (very low) to 5 (great), and 0-3 emotion tags chosen "
        f"ONLY from this exact list: {valid_tags}. If the photo is not a "
        "personal photo (e.g. a pet, meme, object, landscape) or you can't "
        "tell, set is_personal_photo to false."
    )

    try:
        client = genai.Client(api_key=api_key)
        parts = _build_user_parts(message) + [types.Part.from_text(text=instruction)]
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_MoodSuggestion,
            ),
        )
        data = response.parsed
        if not data or not data.is_personal_photo:
            return None
        mood = max(1, min(5, int(data.mood)))
        valid_keys = {key for key, _ in MoodEntry.EMOTION_CHOICES}
        emotions = [e for e in data.emotions if e in valid_keys][:3]
        return {"mood": mood, "emotions": emotions}
    except Exception:
        logger.exception("Mood suggestion failed for message %s", message.pk)
        return None
