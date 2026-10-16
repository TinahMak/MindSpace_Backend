from django import forms


class ChatMessageForm(forms.Form):
    content = forms.CharField(required=False, max_length=4000, widget=forms.Textarea)
    image = forms.ImageField(required=False)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("content") and not cleaned.get("image"):
            raise forms.ValidationError("Type a message or attach a photo before sending.")
        return cleaned
