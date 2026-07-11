import uuid

from django.db import models
from django.conf import settings


class LeadStatus(models.TextChoices):
    NEW_LEAD = "new_lead", "New Lead"
    ENQUIRY = "enquiry", "Enquiry"
    OPPORTUNITY = "opportunity", "Opportunity"
    HOT = "hot", "Hot"
    ON_HOLD = "on_hold", "On Hold"
    NOT_RESPONDING = "not_responding", "Not Responding"
    NOT_REACHABLE = "not_reachable", "Not Reachable"
    DEAD = "dead", "Dead"
    JUNK = "junk", "Junk"
    REPEATED_LEAD = "repeated_lead", "Repeated Lead"
    CONVERTED = "converted", "Converted"


class ActivityType(models.TextChoices):
    CALL = "Call", "Call"
    EMAIL = "Email", "Email"
    WHATSAPP = "WhatsApp", "WhatsApp"
    SMS = "SMS", "SMS"
    MEETING = "Meeting", "Meeting"
    DEMO = "Demo", "Demo"
    FOLLOW_UP = "Follow-up", "Follow-up"


class CompletionStatus(models.TextChoices):
    PENDING = "Pending", "Pending"
    COMPLETED = "Completed", "Completed"


class Lead(models.Model):
    """A webinar lead. `is_new` mirrors the frontend's New Leads / All Leads
    split: leads start as new (e.g. fresh from a CSV import) and move to
    All Leads once they're edited or get their first Activity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_new = models.BooleanField(default=True)

    sl_no = models.CharField(max_length=20, blank=True)

    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    name = models.CharField(max_length=255, blank=True)

    phone = models.CharField(max_length=30, blank=True)
    email = models.CharField(max_length=255, blank=True)

    organization = models.CharField(max_length=255, blank=True)
    job_title = models.CharField(max_length=255, blank=True)
    # Free-text on purpose — source CSVs aren't guaranteed to give a clean number
    # (e.g. "5+ years"), so this mirrors the frontend's string field.
    experience = models.CharField(max_length=50, blank=True)
    salary = models.CharField(max_length=50, blank=True)

    attended = models.CharField(max_length=50, blank=True)
    time = models.CharField(max_length=50, blank=True)
    result = models.CharField(max_length=255, blank=True)

    # SPOC from the source sheet. Set on create only — the frontend/serializer
    # must treat this as read-only on update (see note in reply).
    owner = models.CharField(max_length=120, blank=True)
    owner_email = models.EmailField(blank=True, default="")
    
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leads",
    )
    
    # Country code is stored separately from the number so the digits coming
    # out of the CSV stay clean. Defaults to India for every lead, including
    # CSV imports (which never supply one).
    phone_country_code = models.CharField(max_length=8, blank=True, default="+91")

    # Secondary contact — never comes from the CSV, only ever entered by hand
    # in the Create Activity modal.
    secondary_phone = models.CharField(max_length=32, blank=True, default="")
    secondary_phone_country_code = models.CharField(max_length=8, blank=True, default="+91")
    secondary_email = models.CharField(max_length=254, blank=True, default="")

    # Free CharField (not strictly enforced choices) so unrecognized CSV
    # status text can still be stored, same approach as the frontend.
    status = models.CharField(
        max_length=50, choices=LeadStatus.choices, default=LeadStatus.NEW_LEAD
    )
    
    price_quoted = models.CharField(max_length=64, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"Lead {self.id}"

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = " ".join(
                part for part in [self.first_name, self.last_name] if part
            ).strip()
        super().save(*args, **kwargs)


class Activity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(
        Lead, related_name="activities", on_delete=models.CASCADE
    )

    type = models.CharField(max_length=30, choices=ActivityType.choices)
    description = models.TextField(blank=True)
    owner = models.CharField(max_length=120, blank=True)

    due_date = models.DateField(null=True, blank=True)
    time = models.CharField(max_length=20, blank=True)

    lead_status = models.CharField(
        max_length=50, choices=LeadStatus.choices, default=LeadStatus.NEW_LEAD
    )
    completion_status = models.CharField(
        max_length=20,
        choices=CompletionStatus.choices,
        default=CompletionStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-due_date", "-created_at"]
        verbose_name_plural = "activities"

    def __str__(self):
        return f"{self.type} — {self.lead.name}"