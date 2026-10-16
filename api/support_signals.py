"""
Decides when the chat should offer "Would you like to talk to a professional?".

Deterministic word lists (not the AI), so the behaviour is predictable and
testable. It never replaces crisis handling: crisis messages are flagged by
aichat.services.detect_crisis first, and the app shows the crisis line above
the professional option.
"""

import re

# The person is asking for professional help directly.
ASKING = [
    "therapist", "therapy", "psychologist", "psychiatrist", "counsellor", "counselor", "counselling",
    "counseling", "social worker", "professional help", "see a doctor", "speak to a doctor",
    "talk to a doctor", "someone to talk to", "need to talk to someone", "i need help", "get help",
]

# Signs of ongoing distress that a professional could help with.
DISTRESS = [
    "depressed", "depression", "hopeless", "worthless", "can't cope", "cant cope", "cannot cope",
    "can't handle", "cant handle", "can't take it", "cant take it", "falling apart", "breaking down",
    "panic attack", "anxiety attack", "anxious all the time", "can't stop crying", "cant stop crying",
    "crying every day", "can't sleep", "cant sleep", "cannot sleep", "no one to talk to", "nobody to talk to",
    "so alone", "so lonely", "overwhelmed", "burnt out", "burned out", "burnout", "traumatised", "traumatized",
    "grieving", "can't go on like this", "cant go on like this", "too much for me",
]


def _norm(text):
    text = (text or "").lower().replace("’", "'")
    return re.sub(r"\s+", " ", text)


def _has(text, phrases):
    return any(re.search(r"(?<![a-z])" + re.escape(p) + r"(?![a-z])", text) for p in phrases)


def support_signal(text, is_crisis=False):
    """Returns 'crisis', 'asked', 'distress' or None."""
    if is_crisis:
        return "crisis"
    t = _norm(text)
    if not t:
        return None
    if _has(t, ASKING):
        return "asked"
    if _has(t, DISTRESS):
        return "distress"
    return None
