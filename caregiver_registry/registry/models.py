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
    ("caregiver", "Caregiver"),
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
# Caregivers and Clients
# ==============================================
STATUS_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]


class Caregiver(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )
    skills = models.TextField(blank=True)
    availability = models.TextField(blank=True)
    preferences = models.TextField(blank=True)
    profile_completed = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Client(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )
    care_needs = models.TextField(blank=True)
    schedule = models.TextField(blank=True)
    preferences = models.TextField(blank=True)
    profile_completed = models.BooleanField(default=False)

    def __str__(self):
        return self.name