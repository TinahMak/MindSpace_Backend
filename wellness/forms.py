from django import forms

from .models import MoodEntry


class MoodCheckInForm(forms.Form):
    mood = forms.TypedChoiceField(
        choices=MoodEntry.MOOD_CHOICES, coerce=int, error_messages={"required": "Please select how you're feeling."}
    )
    emotions = forms.MultipleChoiceField(
        choices=MoodEntry.EMOTION_CHOICES, required=False
    )
    note = forms.CharField(required=False, max_length=500, widget=forms.Textarea)
