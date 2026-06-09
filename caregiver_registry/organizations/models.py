from django.db import models
from django.conf import settings
import uuid
from datetime import timedelta
from django.utils import timezone


STAFF_ROLE_CHOICES = [
    ("admin", "Admin"),
    ("staff", "Staff"),
]


MEMBERSHIP_STATUS_CHOICES = [
    ("invited", "Invited"),
    ("active", "Active"),
    ("inactive", "Inactive"),
]


class Organization(models.Model):
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=10, blank=True)

    primary_admin = models.ForeignKey(
        "accounts.StaffProfile",
        on_delete=models.PROTECT,
        related_name="owned_organizations"
    )

    contact_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ==============================================
# Organization Staff and Invites    
# ==============================================

class OrganizationStaff(models.Model):
    """
    Junction table linking staff to organizations.
    Staff can belong to multiple organizations.
    """
    ROLE_CHOICES = STAFF_ROLE_CHOICES
    STATUS_CHOICES = MEMBERSHIP_STATUS_CHOICES

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="staff_members"
    )

    staff_profile = models.ForeignKey(
        "accounts.StaffProfile",
        on_delete=models.CASCADE,
        related_name="organization_relationships"
    )

    role = models.CharField(
        max_length=20,
        choices=STAFF_ROLE_CHOICES,
        default="staff"
    )

    status = models.CharField(
        max_length=20,
        choices=MEMBERSHIP_STATUS_CHOICES,
        default="active"
    )

    can_view_dashboard = models.BooleanField(default=True)
    can_approve_applications = models.BooleanField(default=False)
    can_invite_staff = models.BooleanField(default=False)
    
    invited_by = models.ForeignKey(
        "accounts.UserProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_invites_sent"
    )
    
    accepted_at = models.DateTimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "staff_profile")
        indexes = [
            models.Index(fields=["organization", "role", "status"]),
            models.Index(fields=["staff_profile", "status"]),
        ]

    def __str__(self):
        return f"{self.staff_profile} - {self.organization} - {self.role}"


# ==============================================
# Organization Staff Invites    
# ==============================================

def default_staff_invite_expiration():
    return timezone.now() + timedelta(days=7)


class OrganizationStaffInvite(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="staff_invites"
    )

    email = models.EmailField()

    role = models.CharField(
        max_length=20,
        choices=STAFF_ROLE_CHOICES,
        default="staff"
    )

    token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )

    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        default=default_staff_invite_expiration
    )

    def __str__(self):
        return f"{self.email} invited to {self.organization}"
