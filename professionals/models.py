import os
import uuid

from django.conf import settings
from django.db import models

from .choices import DOC_KINDS, PROFESSIONS, REGULATORS


class ProfessionalProfile(models.Model):
    PENDING, APPROVED, REJECTED, SUSPENDED = "pending", "approved", "rejected", "suspended"
    STATUS_CHOICES = [(PENDING, "Pending review"), (APPROVED, "Approved"), (REJECTED, "Rejected"), (SUSPENDED, "Suspended")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="professional")
    title = models.CharField(max_length=8, blank=True)
    profession = models.CharField(max_length=32, choices=PROFESSIONS)
    regulator = models.CharField(max_length=8, choices=REGULATORS)
    regulator_other = models.CharField(max_length=100, blank=True)
    registration_number = models.CharField(max_length=40)
    qualifications = models.TextField(max_length=1000)
    years_experience = models.PositiveSmallIntegerField(default=0)
    bio = models.TextField(blank=True, max_length=1500)
    specialties = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)

    practice_name = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=80)
    province = models.CharField(max_length=40)
    latitude = models.FloatField(null=True, blank=True)   # filled in Phase 3 for "near me"
    longitude = models.FloatField(null=True, blank=True)
    offers_in_person = models.BooleanField(default=True)
    offers_online = models.BooleanField(default=False)
    fee_min = models.PositiveIntegerField(null=True, blank=True)  # rand per session
    fee_max = models.PositiveIntegerField(null=True, blank=True)
    accepts_medical_aid = models.BooleanField(default=False)
    contact_phone = models.CharField(max_length=20, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    status_reason = models.CharField(max_length=500, blank=True)
    created_by_admin = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.display_name} ({self.get_profession_display()}, {self.status})"

    @property
    def display_name(self):
        name = f"{self.user.first_name} {self.user.last_name}".strip() or self.user.email
        return f"{self.title} {name}".strip()


def _doc_path(instance, filename):
    # Unguessable name; the original name is kept in the database only.
    ext = os.path.splitext(filename)[1].lower()[:8]
    return f"professional_docs/{uuid.uuid4().hex}{ext}"


class ProfessionalDocument(models.Model):
    profile = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=16, choices=DOC_KINDS, default="qualification")
    file = models.FileField(upload_to=_doc_path)
    original_name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=80)
    size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def delete(self, *args, **kwargs):
        storage, name = self.file.storage, self.file.name
        super().delete(*args, **kwargs)
        if name:
            storage.delete(name)


class ConsultationRequest(models.Model):
    """A client asks an approved professional for a consultation; the professional quotes."""

    REQUESTED, QUOTED, ACCEPTED = "requested", "quoted", "accepted"
    DECLINED_BY_CLIENT, DECLINED_BY_PRO, CANCELLED, EXPIRED = "declined", "pro_declined", "cancelled", "expired"
    STATUS_CHOICES = [
        (REQUESTED, "Waiting for a quote"),
        (QUOTED, "Quote received"),
        (ACCEPTED, "Accepted"),
        (DECLINED_BY_CLIENT, "Quote declined"),
        (DECLINED_BY_PRO, "Declined by the professional"),
        (CANCELLED, "Cancelled"),
        (EXPIRED, "Quote expired"),
    ]
    OPEN = (REQUESTED, QUOTED)
    MODES = [("in_person", "In person"), ("online", "Online"), ("either", "Either")]

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consultation_requests")
    professional = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE, related_name="consultation_requests")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=REQUESTED)

    # what the client chose to share
    mode = models.CharField(max_length=10, choices=MODES, default="either")
    topics = models.JSONField(default=list, blank=True)
    message = models.TextField(blank=True, max_length=1000)
    preferred_times = models.CharField(max_length=200, blank=True)
    mood_summary = models.TextField(blank=True)  # consented snapshot, numbers only
    phone = models.CharField(max_length=20, blank=True)  # only if they chose to share it

    # the professional's quote
    fee = models.PositiveIntegerField(null=True, blank=True)
    duration_min = models.PositiveSmallIntegerField(null=True, blank=True)
    quote_mode = models.CharField(max_length=10, blank=True)
    slots = models.JSONField(default=list, blank=True)
    quote_note = models.TextField(blank=True, max_length=1000)
    valid_until = models.DateField(null=True, blank=True)
    chosen_slot = models.CharField(max_length=80, blank=True)
    response_note = models.CharField(max_length=500, blank=True)  # decline reasons

    created_at = models.DateTimeField(auto_now_add=True)
    quoted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
