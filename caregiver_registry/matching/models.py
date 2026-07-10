"""
Matching models for the three-party caregiver/client/staff match workflow.

A Match requires approval from all three parties (caregiver, client, staff)
before it becomes active. Any party declining cancels the match.
"""

from django.db import models
from django.utils import timezone


# ==============================================
# Tag Model
# ==============================================

class Tag(models.Model):
    """
    Hashtag-style labels used for caregiver/client matching, filtering,
    and AI-assisted scoring.

    Examples: transfers, wheelchair, dementia, cooking, lgbtq, fragrance-free
    """
    name = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Lowercase slug, e.g. 'wheelchair' or 'fragrance-free'"
    )
    label = models.CharField(
        max_length=150,
        help_text="Human-readable label shown in the UI"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of what this tag covers"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive tags are hidden from selection UIs"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Tag"
        verbose_name_plural = "Tags"

    def __str__(self):
        return f"#{self.name}"


# ==============================================
# Notification Model
# ==============================================

class Notification(models.Model):
    """
    In-app notification stored in the database.
    Used as a fallback when email cannot be sent, and as a primary channel
    for match-related events.
    """
    NOTIFICATION_TYPES = [
        ("match_request", "Match Request"),
        ("match_approved", "Match Approved"),
        ("match_declined", "Match Declined"),
        ("match_active", "Match Active"),
        ("match_cancelled", "Match Cancelled"),
        ("general", "General"),
    ]

    recipient = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPES,
        default="general"
    )

    subject = models.CharField(max_length=255)
    message = models.TextField()

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional link to a related match
    match = models.ForeignKey(
        "matching.Match",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["recipient", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] → {self.recipient.display_name}: {self.subject}"


# ==============================================
# Match Status Choices
# ==============================================

INITIATED_BY_CHOICES = [
    ("caregiver", "Caregiver"),
    ("client", "Client"),
    ("staff", "Staff"),
    ("ai", "AI"),
]

PARTY_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("declined", "Declined"),
]

OVERALL_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("active", "Active"),
    ("declined", "Declined"),
    ("cancelled", "Cancelled"),
]


# ==============================================
# Match Model
# ==============================================

class Match(models.Model):
    """
    Represents a proposed caregiver-client match.

    A match requires approval from both the caregiver and client to become active:
      - caregiver_status = approved
      - client_status = approved
      → overall status becomes 'active'

    Staff no longer approve/decline matches; they can only track and view them for analytics.
    If either caregiver or client declines, overall status becomes 'declined'.

    The initiating party is automatically set to 'approved' when the match is created.
    Staff/AI-initiated matches set staff_status='approved' for record-keeping
    but do not require staff approval to become active.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="matches",
        help_text="The organization under which this match is proposed"
    )

    caregiver = models.ForeignKey(
        "registry.CaregiverProfile",
        on_delete=models.CASCADE,
        related_name="matches"
    )

    client = models.ForeignKey(
        "registry.ClientProfile",
        on_delete=models.CASCADE,
        related_name="matches"
    )

    initiated_by = models.CharField(
        max_length=20,
        choices=INITIATED_BY_CHOICES,
        help_text="Which party initiated the match"
    )

    initiated_by_user = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_matches",
        help_text="The specific user who created this match record"
    )

    # ── Per-party approval statuses ──────────────────────────────────────────
    caregiver_status = models.CharField(
        max_length=20,
        choices=PARTY_STATUS_CHOICES,
        default="pending"
    )
    client_status = models.CharField(
        max_length=20,
        choices=PARTY_STATUS_CHOICES,
        default="pending"
    )
    staff_status = models.CharField(
        max_length=20,
        choices=PARTY_STATUS_CHOICES,
        default="pending"
    )

    # ── Overall computed status ───────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=OVERALL_STATUS_CHOICES,
        default="pending",
        db_index=True
    )

    # ── Scoring and AI fields ─────────────────────────────────────────────────
    match_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Numeric compatibility score (0–100)"
    )
    match_details = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Structured breakdown of match factors: tag overlap, availability, "
            "location, transportation, etc."
        )
    )
    selected_tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="matches",
        help_text="Tags selected when this match was created"
    )
    ai_reasoning = models.TextField(
        blank=True,
        help_text="Human-readable explanation of match quality from AI or local scorer"
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = models.TextField(
        blank=True,
        help_text="Optional staff notes about this match"
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Match"
        verbose_name_plural = "Matches"
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["caregiver", "status"]),
            models.Index(fields=["client", "status"]),
            models.Index(fields=["caregiver", "client", "status"]),
        ]

    def __str__(self):
        return (
            f"Match #{self.pk}: "
            f"{self.caregiver.user_profile.display_name} ↔ "
            f"{self.client.user_profile.display_name} [{self.status}]"
        )

    # ── Status Transition Methods ─────────────────────────────────────────────

    def _recompute_overall_status(self):
        """
        Recompute and save the overall status based on caregiver and client statuses.

        Rules (two-party workflow):
          - Caregiver or client 'declined' → overall 'declined'
          - Both caregiver and client 'approved' → overall 'active'
          - Otherwise → 'pending'

        Staff status is stored for record-keeping only and does not affect
        the overall status.

        Does NOT call save(); callers must save the instance.
        """
        if (
            self.caregiver_status == "declined"
            or self.client_status == "declined"
        ):
            self.status = "declined"
        elif (
            self.caregiver_status == "approved"
            and self.client_status == "approved"
        ):
            self.status = "active"
        else:
            self.status = "pending"

    def apply_initiator_status(self):
        """
        Set the initiating party's status to 'approved' immediately.
        Should be called once before first save().
        """
        if self.initiated_by == "caregiver":
            self.caregiver_status = "approved"
        elif self.initiated_by == "client":
            self.client_status = "approved"
        elif self.initiated_by in ("staff", "ai"):
            self.staff_status = "approved"
        self._recompute_overall_status()

    def caregiver_approve(self):
        """Caregiver approves the match."""
        self.caregiver_status = "approved"
        self._recompute_overall_status()
        self.save()

    def caregiver_decline(self):
        """Caregiver declines the match."""
        self.caregiver_status = "declined"
        self._recompute_overall_status()
        self.save()

    def client_approve(self):
        """Client approves the match."""
        self.client_status = "approved"
        self._recompute_overall_status()
        self.save()

    def client_decline(self):
        """Client declines the match."""
        self.client_status = "declined"
        self._recompute_overall_status()
        self.save()

    def staff_approve(self):
        """Staff approves the match."""
        self.staff_status = "approved"
        self._recompute_overall_status()
        self.save()

    def staff_decline(self):
        """Staff declines the match."""
        self.staff_status = "declined"
        self._recompute_overall_status()
        self.save()

    def cancel(self):
        """Cancel a pending match (admin or initiator action)."""
        self.status = "cancelled"
        self.save()

    # ── Convenience Properties ────────────────────────────────────────────────

    @property
    def is_active(self):
        return self.status == "active"

    @property
    def is_pending(self):
        return self.status == "pending"

    @property
    def is_declined(self):
        return self.status == "declined"

    @property
    def pending_parties(self):
        """
        Returns a list of party names whose approval is still pending.
        Only caregiver and client participate in match approval.
        """
        pending = []
        if self.caregiver_status == "pending":
            pending.append("caregiver")
        if self.client_status == "pending":
            pending.append("client")
        return pending
