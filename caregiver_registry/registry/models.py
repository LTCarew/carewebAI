from django.db import models
from organizations.models import Organization
import uuid
from django.utils import timezone
from datetime import timedelta

def default_invite_expiration():
    return timezone.now() + timedelta(days=7)

# ==============================================
# Invites
# ==============================================
ROLE_CHOICES = [
    ("caregiver", "Careworker"),
    ("client", "Client"),
]


class Invite(models.Model):
    email = models.EmailField()
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        default=default_invite_expiration
    )
    accepted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.email} - {self.role}"


# ==============================================
# Shared Choices
# ==============================================
STATUS_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("inactive", "Inactive"),
]


CONTACT_PREFERENCES = [
    ("phone", "Phone"),
    ("email", "Email"),
    ("text", "Text Message"),
    ("any", "Any"),
]


PRONOUN_CHOICES = [
    ("she_her", "She/Her"),
    ("he_him", "He/Him"),
    ("they_them", "They/Them"),
    ("she_they", "She/They"),
    ("he_they", "He/They"),
    ("ze_zir", "Ze/Zir"),
    ("ask_me", "Ask Me"),
    ("self_describe", "Self Describe"),
]


TRANSPORTATION_CHOICES = [
    ("licensed_driver", "Licensed Driver"),
    ("vehicle_access", "Reliable access to a vehicle"),
    ("wheelchair_vehicle", "Comfortable driving or learning wheelchair accessible vehicles"),
    ("insured", "Insured"),
    ("comfortable_driving_others", "Comfortable driving others"),
    ("no_driving", "Looking for work that doesn't involve driving"),
]


HOURS_LOOKING_FOR_CHOICES = [
    ("all_welcome", "All are welcome"),
    ("few_hours", "Just a few hours"),
    ("part_time", "Part-Time"),
    ("full_time", "Full Time"),
    ("live_in", "Live-In"),
    ("flexible", "Flexible"),
]


EXPERIENCE_CHOICES = [
    ("domestic_tasks", "Domestic tasks"),
    ("errands", "Willing to run errands"),
    ("bathing", "Bathing assistance"),
    ("cooking", "Cooking / meal preparation"),
    ("dressing", "Dressing assistance"),

    ("assistive_technology", "Assistive Technology Maintenance"),
    ("bowel_programs", "Bowel Programs"),
    ("couple_family", "Caring for a couple/small family"),
    ("catheters", "Catheters"),
    ("chair_users", "Chair Users"),
    ("chronic_illness", "Chronic Illness Disabilities"),
    ("cna", "CNA"),
    ("cognitive_disabilities", "Cognitive Disabilities"),
    ("complex_illnesses", "Complex Illnesses"),
    ("cpr", "CPR Training"),
    ("deaf_community", "d/Deaf community"),
    ("dementia", "Dementia/Alzheimers"),
    ("developmental_disabilities", "Developmental disabilities"),
    ("elders", "Elders/Older Adults"),
    ("emergency_preparedness", "Emergency Preparedness Plans"),
    ("emt", "EMT Training"),
    ("cil_courses", "Enrolled in CIL Caregiver Courses"),
    ("feeding_tubes", "Feeding Tubes"),
    ("fragrance_free", "Fragrance-Free"),
    ("anti_bias", "Has taken anti-bias trainings"),
    ("soft_skills", "Has taken soft skills trainings"),
    ("hoyer_lifts", "Hoyer Lifts"),
    ("ihss", "IHSS"),
    ("lgbtq", "LGBTQ+"),
    ("lifting_transfers", "Lifting/Transfers"),
    ("limited_english", "Multi-Lingual Limited English Speakers"),
    ("person_centered", "Person-centered care"),
    ("spinal_cord", "Spinal Cord Disabilities"),
    ("ventilators", "Ventilators"),
    ("visual_impairments", "Visual impairments"),
]

LANGUAGE_CHOICES = [
    ("english", "English"),
    ("spanish", "Spanish"),
    ("asl", "ASL"),
    ("cantonese", "Cantonese"),
    ("mandarin", "Mandarin"),
    ("portuguese_brazilian", "Portuguese (Brazilian)"),
    ("portuguese_portugal", "Portuguese (Portugal)"),
    ("other_languages", "Other Languages"),
]

PATHOGEN_PROTOCOL_CHOICES = [
    ("n95_at_work", "Willing to mask with N95's at work"),
    ("masking_indoors", "Consistently masking indoors"),
    ("masking_crowded_outdoors", "Consistently masking in crowded spaces outdoors"),
    ("masking_around_others", "Consistently masking around anyone not taking protocols"),
    ("adjust_protocols", "Open to adjusting daily life protocols"),
    ("learn_more", "Interested in learning more about pathogen safety"),
]


RATE_CHOICES = [
    ("17_20", "$17-$20/hr"),
    ("20_25", "$20-$25/hr"),
    ("25_30", "$25-$30/hr"),
    ("30_50", "$30-$50/hr"),
    ("50_plus", "$50+/hr"),
]


ATTENDANT_PROGRAM_CHOICES = [
    ("ihss", "IHSS - In Home Supportive Services"),
    ("wpcs", "WPCS - Waiver Personal Care Services"),
    ("sls", "SLS - Supportive Living Services"),
    ("sdp", "SDP - Self Determination Program"),
    ("out_of_pocket", "Pay out of pocket"),
]


CARE_NEEDS_CHOICES = [
    ("domestic_tasks", "Domestic tasks"),
    ("errands", "Errands"),
    ("bathing", "Bathing"),
    ("cooking", "Cooking"),
    ("dressing", "Dressing"),

    ("assistive_technology", "Assistive technology maintenance"),
    ("bowel_programs", "Bowel programs"),
    ("couple_family", "Care for a couple/small family"),
    ("catheters", "Catheter support"),
    ("chair_users", "Wheelchair / chair user support"),
    ("chronic_illness", "Chronic illness support"),
    ("cognitive_disabilities", "Cognitive disability support"),
    ("complex_illnesses", "Complex illness support"),
    ("deaf_community", "d/Deaf community support"),
    ("dementia", "Dementia/Alzheimer's support"),
    ("developmental_disabilities", "Developmental disability support"),
    ("elders", "Elder / older adult support"),
    ("emergency_preparedness", "Emergency preparedness planning"),
    ("feeding_tubes", "Feeding tube support"),
    ("fragrance_free", "Fragrance-free support needed"),
    ("hoyer_lifts", "Hoyer lift support"),
    ("ihss", "IHSS experience preferred"),
    ("lgbtq", "LGBTQ+ affirming care"),
    ("lifting_transfers", "Lifting / transfers"),
    ("limited_english", "Support for limited English speakers"),
    ("person_centered", "Person-centered care"),
    ("spinal_cord", "Spinal cord disability support"),
    ("ventilators", "Ventilator support"),
    ("visual_impairments", "Visual impairment support"),

    ("cna_preferred", "CNA preferred"),
    ("cpr_preferred", "CPR training preferred"),
    ("emt_preferred", "EMT training preferred"),
    ("anti_bias_preferred", "Anti-bias training preferred"),
    ("soft_skills_preferred", "Soft skills training preferred"),
    ("cil_training_preferred", "CIL caregiver course training preferred"),
]


# ==============================================
# Caregiver and Client Profiles
# ==============================================

class CaregiverProfile(models.Model):
    """
    Stores caregiver-specific information for a person.
    Links to UserProfile for shared contact info.
    """
    user_profile = models.OneToOneField(
        "accounts.UserProfile",
        on_delete=models.CASCADE,
        related_name="caregiver_profile"
    )

    base_zip_code = models.CharField(max_length=10)
    willing_to_work_cities = models.JSONField(default=list, blank=True)

    attendant_care_programs = models.JSONField(default=list, blank=True)

    transportation = models.JSONField(default=list, blank=True)
    availability = models.JSONField(default=dict, blank=True)

    hours_looking_for = models.CharField(
        max_length=50,
        choices=HOURS_LOOKING_FOR_CHOICES
    )

    certified_ihss_worker = models.BooleanField(default=False)
    additional_certifications = models.TextField(blank=True)

    experience_with = models.JSONField(default=list, blank=True)
    languages_spoken = models.JSONField(default=list, blank=True)
    pathogen_protocols = models.JSONField(default=list, blank=True)

    desired_hours_per_week = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Desired number of work hours per week"
    )

    rate = models.CharField(max_length=50, choices=RATE_CHOICES)

    bio = models.TextField(blank=True)

    wants_training_updates = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"CaregiverProfile: {self.user_profile.display_name}"


class ClientProfile(models.Model):
    """
    Stores client-specific care needs and preferences.
    Links to UserProfile for shared contact info.
    """
    user_profile = models.OneToOneField(
        "accounts.UserProfile",
        on_delete=models.CASCADE,
        related_name="client_profile"
    )

    base_zip_code = models.CharField(max_length=10)

    attendant_care_programs = models.JSONField(default=list, blank=True)

    languages_preferred = models.JSONField(default=list, blank=True)

    availability = models.JSONField(default=dict, blank=True)
    schedule_flexibility = models.BooleanField(default=False)
    hours_per_week = models.PositiveIntegerField(null=True, blank=True)

    care_needs = models.JSONField(default=list, blank=True)
    additional_care_needs = models.TextField(blank=True)

    pathogen_protocol_preferences = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ClientProfile: {self.user_profile.display_name}"


# ==============================================
# Organization Relationships (Junction Tables)
# ==============================================

class OrganizationCaregiver(models.Model):
    """
    Junction table linking caregivers to organizations.
    Caregivers can belong to multiple organizations.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="caregiver_relationships"
    )

    caregiver_profile = models.ForeignKey(
        CaregiverProfile,
        on_delete=models.CASCADE,
        related_name="organization_relationships"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    approved_by = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_caregivers"
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "caregiver_profile")
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["caregiver_profile", "status"]),
        ]

    def __str__(self):
        return f"{self.caregiver_profile} - {self.organization} - {self.status}"


class OrganizationClient(models.Model):
    """
    Junction table linking clients to organizations.
    Clients can belong to multiple organizations.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="client_relationships"
    )

    client_profile = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name="organization_relationships"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    approved_by = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_clients"
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "client_profile")
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["client_profile", "status"]),
        ]

    def __str__(self):
        return f"{self.client_profile} - {self.organization} - {self.status}"


# ==============================================
# Support Coordinator Models
# ==============================================

class SupportCoordinatorProfile(models.Model):
    """
    Profile for support coordinators who assist clients.
    Support coordinators are invited by clients and can help manage
    client information and caregiver relationships based on permissions.
    """
    user_profile = models.OneToOneField(
        "accounts.UserProfile",
        on_delete=models.CASCADE,
        related_name="support_coordinator_profile"
    )
    
    # Information about the coordinator
    relationship_to_clients = models.CharField(
        max_length=100,
        help_text="E.g., Family member, Agency representative, Friend, etc."
    )
    credentials = models.TextField(
        blank=True,
        help_text="Professional credentials or qualifications"
    )
    certifications = models.TextField(
        blank=True,
        help_text="Relevant certifications"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Support Coordinator: {self.user_profile.display_name}"
    
    class Meta:
        verbose_name = "Support Coordinator Profile"
        verbose_name_plural = "Support Coordinator Profiles"


class ClientCoordinator(models.Model):
    """
    Junction table linking clients with their support coordinators.
    Includes client-controlled permissions for each coordinator.
    """
    client_profile = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name="coordinator_relationships"
    )
    
    coordinator_profile = models.ForeignKey(
        SupportCoordinatorProfile,
        on_delete=models.CASCADE,
        related_name="client_relationships"
    )
    
    # Client-controlled permissions
    can_edit_profile = models.BooleanField(
        default=False,
        help_text="Can the coordinator edit the client's profile?"
    )
    can_approve_caregivers = models.BooleanField(
        default=False,
        help_text="Can the coordinator approve/reject caregiver matches?"
    )
    
    # Relationship status
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('active', 'Active'),
            ('inactive', 'Inactive')
        ],
        default='pending',
        help_text="Status of the coordinator relationship"
    )
    
    # Tracking
    invited_by = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coordinator_invitations_sent"
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['client_profile', 'coordinator_profile']
        verbose_name = "Client-Coordinator Relationship"
        verbose_name_plural = "Client-Coordinator Relationships"
        indexes = [
            models.Index(fields=["client_profile", "status"]),
            models.Index(fields=["coordinator_profile", "status"]),
        ]
    
    def __str__(self):
        return (
            f"{self.coordinator_profile.user_profile.display_name} → "
            f"{self.client_profile.user_profile.display_name} ({self.status})"
        )


class CoordinatorInvite(models.Model):
    """
    Invitation for someone to become a support coordinator for a client.
    Clients send these invitations via email with a unique token link.
    """
    client_profile = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name="coordinator_invites"
    )
    
    email = models.EmailField(help_text="Email address of the invited coordinator")
    
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Unique token for the invitation link"
    )
    
    invited_by = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.CASCADE,
        related_name="coordinator_invites_created"
    )
    
    # Lifecycle tracking
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        default=default_invite_expiration,
        help_text="Invitation expires 7 days after creation"
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the invitation was accepted"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Coordinator Invitation"
        verbose_name_plural = "Coordinator Invitations"
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["client_profile", "email"]),
        ]
    
    def __str__(self):
        return f"Invite for {self.email} to support {self.client_profile.user_profile.display_name}"
    
    def is_expired(self):
        """Check if the invitation has expired."""
        return timezone.now() > self.expires_at
    
    def is_used(self):
        """Check if the invitation has been used."""
        return self.used_at is not None
    
    def is_valid(self):
        """Check if the invitation is still valid (not expired and not used)."""
        return not self.is_expired() and not self.is_used()


# ==============================================
# Scheduling Models
# ==============================================

SCHEDULE_STATUS_CHOICES = [
    ("draft",                "Draft"),
    ("submitted",            "Submitted"),
    ("partially_approved",   "Partially Approved"),
    ("approved",             "Approved"),
    ("rejected",             "Rejected"),
    ("cancelled",            "Cancelled"),
]

SCHEDULE_FREQUENCY_CHOICES = [
    ("weekly",    "Weekly"),
    ("biweekly",  "Bi-weekly (every 2 weeks)"),
    ("custom",    "Custom interval"),
]

ENTRY_REVIEW_STATUS_CHOICES = [
    ("pending",  "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]

DAY_OF_WEEK_CHOICES = [
    ("monday",    "Monday"),
    ("tuesday",   "Tuesday"),
    ("wednesday", "Wednesday"),
    ("thursday",  "Thursday"),
    ("friday",    "Friday"),
    ("saturday",  "Saturday"),
    ("sunday",    "Sunday"),
]


class Schedule(models.Model):
    """
    A proposed work schedule created by a client for a matched caregiver.
    May also include a support person (coordinator) who must co-approve each entry.

    Lifecycle:
      draft → submitted → (partially_approved | approved | rejected) | cancelled

    Editing is only allowed while status == 'draft'.
    After submission the client must cancel and recreate to make changes.
    """
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    client = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    caregiver = models.ForeignKey(
        CaregiverProfile,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    support_person = models.ForeignKey(
        SupportCoordinatorProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules",
        help_text="Optional support person/coordinator who also approves this schedule",
    )
    match = models.ForeignKey(
        "matching.Match",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules",
        help_text="The active match this schedule is attached to",
    )
    created_by = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_schedules",
    )

    status = models.CharField(
        max_length=30,
        choices=SCHEDULE_STATUS_CHOICES,
        default="draft",
        db_index=True,
    )

    # ── Recurrence ────────────────────────────────────────────────────────────
    start_date = models.DateField(
        help_text="Date this schedule begins (first day of service)",
    )
    frequency = models.CharField(
        max_length=20,
        choices=SCHEDULE_FREQUENCY_CHOICES,
        default="weekly",
        help_text="How often the schedule repeats",
    )
    custom_interval_weeks = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of weeks between visits (required when frequency is 'Custom')",
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional last date of service. Leave blank for ongoing.",
    )

    notes = models.TextField(blank=True, help_text="Optional notes from the client")

    submitted_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Schedule"
        verbose_name_plural = "Schedules"
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["client", "status"]),
            models.Index(fields=["caregiver", "status"]),
        ]

    def __str__(self):
        return (
            f"Schedule #{self.pk}: "
            f"{self.client.user_profile.display_name} → "
            f"{self.caregiver.user_profile.display_name} [{self.status}]"
        )

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_editable_by_client(self):
        """Clients can only edit while the schedule is a draft."""
        return self.status == "draft"

    @property
    def is_submitted(self):
        return self.status != "draft"

    @property
    def all_entries_caregiver_approved(self):
        return self.entries.exists() and not self.entries.exclude(
            caregiver_status="approved"
        ).exists()

    @property
    def all_entries_support_person_approved(self):
        if self.support_person is None:
            return True  # no support person required
        return self.entries.exists() and not self.entries.exclude(
            support_person_status="approved"
        ).exists()

    @property
    def has_rejections(self):
        return self.entries.filter(
            caregiver_status="rejected"
        ).exists() or self.entries.filter(
            support_person_status="rejected"
        ).exists()

    @property
    def approval_progress(self):
        """
        Returns (caregiver_approved_count, support_approved_count, total_count).
        Useful for displaying progress in dashboards.
        """
        total = self.entries.count()
        cg_approved = self.entries.filter(caregiver_status="approved").count()
        sp_approved = self.entries.filter(support_person_status="approved").count()
        return cg_approved, sp_approved, total

    # ── Status Recalculation ──────────────────────────────────────────────────

    def update_status_from_entries(self):
        """
        Recalculate and save overall schedule status based on entry statuses.

        Rules:
          - Any caregiver or support_person entry is 'rejected' → 'rejected'
          - All entries approved by both caregiver and support_person → 'approved'
          - Some entries approved, others still pending → 'partially_approved'
          - All still pending → remains 'submitted'
        """
        if self.status in ("draft", "cancelled"):
            return  # do not auto-update these statuses

        entries = list(self.entries.all())
        if not entries:
            return

        if any(
            e.caregiver_status == "rejected" or e.support_person_status == "rejected"
            for e in entries
        ):
            self.status = "rejected"
            self.save(update_fields=["status", "updated_at"])
            return

        cg_all_ok = all(e.caregiver_status == "approved" for e in entries)
        sp_all_ok = all(
            e.support_person_status == "approved"
            for e in entries
        ) if self.support_person else True

        if cg_all_ok and sp_all_ok:
            self.status = "approved"
        elif any(
            e.caregiver_status == "approved" or e.support_person_status == "approved"
            for e in entries
        ):
            self.status = "partially_approved"
        else:
            self.status = "submitted"

        self.save(update_fields=["status", "updated_at"])


class ScheduleEntry(models.Model):
    """
    A single day/time slot within a Schedule.
    Each entry requires independent approval from the caregiver and (if assigned)
    the support person/coordinator.
    """
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    day_of_week = models.CharField(
        max_length=15,
        choices=DAY_OF_WEEK_CHOICES,
        help_text="Day of the week for this recurring slot",
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    # ── Caregiver review ─────────────────────────────────────────────────────
    caregiver_status = models.CharField(
        max_length=10,
        choices=ENTRY_REVIEW_STATUS_CHOICES,
        default="pending",
    )
    caregiver_reviewed_at = models.DateTimeField(null=True, blank=True)
    caregiver_notes = models.TextField(
        blank=True,
        help_text="Optional note from caregiver when rejecting",
    )

    # ── Support person review ────────────────────────────────────────────────
    support_person_status = models.CharField(
        max_length=10,
        choices=ENTRY_REVIEW_STATUS_CHOICES,
        default="pending",
    )
    support_person_reviewed_at = models.DateTimeField(null=True, blank=True)
    support_person_notes = models.TextField(
        blank=True,
        help_text="Optional note from support person when rejecting",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "day_of_week",
            "start_time",
        ]
        verbose_name = "Schedule Entry"
        verbose_name_plural = "Schedule Entries"
        unique_together = [("schedule", "day_of_week", "start_time", "end_time")]

    def __str__(self):
        return (
            f"{self.get_day_of_week_display()} "
            f"{self.start_time:%I:%M %p}–{self.end_time:%I:%M %p} "
            f"[cg:{self.caregiver_status} / sp:{self.support_person_status}]"
        )

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

    @property
    def is_fully_approved(self):
        """True when both the caregiver has approved AND support_person approved (or no support_person)."""
        cg_ok = self.caregiver_status == "approved"
        sp_ok = (
            self.support_person_status == "approved"
            if self.schedule.support_person_id
            else True
        )
        return cg_ok and sp_ok


# ==============================================
# Schedule Entry Ratings
# ==============================================

RATER_ROLE_CHOICES = [
    ("client",    "Client"),
    ("caregiver", "Caregiver"),
]


class ScheduleEntryRating(models.Model):
    """
    Post-session experience rating for a single ScheduleEntry day slot.
    Both the client and caregiver each submit their own side independently.
    """
    schedule_entry = models.ForeignKey(
        ScheduleEntry,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    rater_profile = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.CASCADE,
        related_name="schedule_ratings_given",
    )
    rater_role = models.CharField(
        max_length=10,
        choices=RATER_ROLE_CHOICES,
        help_text="Whether the rater is the client or careworker in this schedule.",
    )
    rating_date = models.DateField(
        help_text="The specific calendar date this session occurred on.",
    )

    # ── 4 shared metrics (1=Poor, 10=Excellent) ──────────────────────────────
    care_fit_respect = models.PositiveSmallIntegerField(
        help_text="1–10. Care Fit & Respect: mutual understanding of needs, preferences, and boundaries.",
    )
    communication_coordination = models.PositiveSmallIntegerField(
        help_text="1–10. Communication & Coordination: clarity, responsiveness, and problem-solving.",
    )
    reliability_consistency = models.PositiveSmallIntegerField(
        help_text="1–10. Reliability & Consistency: attendance, punctuality, and follow-through.",
    )
    workload_support_balance = models.PositiveSmallIntegerField(
        help_text="1–10. Workload & Support Balance: sustainability and appropriate support for all parties.",
    )

    notes = models.TextField(
        blank=True,
        help_text="Optional notes or context for this rating.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-rating_date", "-created_at"]
        verbose_name = "Schedule Entry Rating"
        verbose_name_plural = "Schedule Entry Ratings"
        unique_together = [("schedule_entry", "rater_profile", "rating_date")]

    def __str__(self):
        return (
            f"{self.rater_role} rating for entry {self.schedule_entry_id} "
            f"on {self.rating_date} — avg {self.average:.1f}"
        )

    @property
    def average(self):
        return (
            self.care_fit_respect
            + self.communication_coordination
            + self.reliability_consistency
            + self.workload_support_balance
        ) / 4
