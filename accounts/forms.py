from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()

MIN_AGE = 16


class SignupForm(forms.ModelForm):
    """
    Mirrors the 3-step signup form's fields and validation:
    name, email, DOB (16+), password + confirm, focus, phone (optional),
    terms + age confirmation checkboxes, marketing opt-in.
    """

    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    date_of_birth = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    focus = forms.ChoiceField(choices=[("", "Select a reason")] + User.FOCUS_CHOICES, required=True)
    phone = forms.CharField(required=False)
    terms = forms.BooleanField(required=True)
    age_confirm = forms.BooleanField(required=True)
    marketing = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "email", "date_of_birth",
            "focus", "phone",
        ]

    def clean_email(self):
        from api.validators import InputError, clean_email

        try:
            email = clean_email(self.cleaned_data["email"])
        except InputError as e:
            raise forms.ValidationError(str(e))
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        age = (date.today() - dob).days // 365
        if age < MIN_AGE:
            raise forms.ValidationError(f"You must be at least {MIN_AGE} years old to use MindSpace.")
        return dob

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if phone:
            import re
            if not re.match(r"^[+]?[\d\s\-().]{7,15}$", phone):
                raise forms.ValidationError("Please enter a valid phone number.")
        return phone

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if pwd and confirm and pwd != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        from django.utils import timezone

        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.set_password(self.cleaned_data["password"])
        user.marketing_opt_in = self.cleaned_data.get("marketing", False)
        user.terms_accepted_at = timezone.now()
        if commit:
            user.save()
        return user


class EmailLoginForm(AuthenticationForm):
    """Login form using email instead of username as the identifier."""

    username = forms.EmailField(label="Email address")


class DeleteAccountForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label="Confirm your password")
