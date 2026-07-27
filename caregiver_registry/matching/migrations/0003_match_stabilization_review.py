"""
Migration: Add stabilization-review tracking fields to Match.

These fields let staff flag a specific caregiver–client relationship for
follow-up via the Stability Snapshot feature. They are minimal by design —
the actual stability status is computed on-the-fly from existing rating data.
"""
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("matching", "0002_seed_default_tags"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="stabilization_review_requested",
            field=models.BooleanField(
                default=False,
                help_text="True when an authorized staff member has flagged this relationship for stabilization review.",
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="stabilization_review_requested_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="Timestamp when the stabilization review was first requested.",
            ),
        ),
        migrations.AddField(
            model_name="match",
            name="stabilization_review_requested_by",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="requested_stabilization_reviews",
                to="accounts.userprofile",
                help_text="The staff member who requested the stabilization review.",
            ),
        ),
    ]
