from django.conf import settings
from django.db import models

from organizations.models import Organization


class UserProfile(models.Model):
    USER_TYPE_CHOICES = [
        ("caregiver", "Caregiver"),
        ("client", "Client"),
        ("admin_staff", "Admin Staff"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="user_profiles",
        null=True,
        blank=True
    )

    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES
    )

    def __str__(self):
        return f"{self.user.username} - {self.user_type}"