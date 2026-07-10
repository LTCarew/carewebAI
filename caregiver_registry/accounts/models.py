from django.conf import settings
from django.db import models


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

CONTACT_PREFERENCES = [
    ("phone", "Phone"),
    ("email", "Email"),
    ("text", "Text Message"),
    ("any", "Any"),
]


class UserProfile(models.Model):
    """
    Stores shared contact/preference information for a user.
    Identity fields (name, email) come from the linked auth User:
        user.first_name, user.last_name, user.email
    Use the display_name / auth_email properties for display.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    # Contact / preferences — identity lives on auth User
    phone = models.CharField(max_length=25, blank=True)

    pronouns = models.CharField(
        max_length=50,
        choices=PRONOUN_CHOICES,
        blank=True
    )

    contact_preferences = models.JSONField(default=list, blank=True)

    # Optional address (primarily for clients, but available for all)
    address = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    # ------------------------------------------------------------------
    # Convenience read-only properties — sourced from auth User
    # ------------------------------------------------------------------

    @property
    def display_name(self):
        """Full name from auth User, falling back to username."""
        return self.user.get_full_name().strip() or self.user.username

    @property
    def auth_email(self):
        """Email from auth User."""
        return self.user.email

    def __str__(self):
        return f"{self.display_name} ({self.user.email})"


class StaffProfile(models.Model):
    """
    Stores staff-specific information for a person.

    Organization-specific staff details like role, status, invite acceptance,
    and start date live on organizations.OrganizationStaff so a staff person can
    belong to multiple organizations without duplicating their person profile.
    """
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="staff_profile"
    )

    title = models.CharField(max_length=150, blank=True)
    hiring_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"StaffProfile: {self.user_profile.display_name}"
