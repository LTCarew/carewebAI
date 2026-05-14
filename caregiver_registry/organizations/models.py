from django.db import models
from django.conf import settings
import uuid
from datetime import timedelta
from django.utils import timezone

class Organization(models.Model):
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=10, blank=True)

    primary_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("staff", "Staff"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="staff_members"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_staff_roles"
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="staff"
    )

    can_view_dashboard = models.BooleanField(default=True)
    can_approve_applications = models.BooleanField(default=False)
    can_invite_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.organization} - {self.role}"

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
        choices=OrganizationStaff.ROLE_CHOICES,
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