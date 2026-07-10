"""
Migration: Add recurrence fields to Schedule.

New fields:
  - start_date       (DateField, required — existing rows get 2026-07-10 as default)
  - frequency        (CharField, default="weekly")
  - custom_interval_weeks (PositiveIntegerField, nullable)
  - end_date         (DateField, nullable)
"""
import datetime
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0004_alter_invite_role_schedule_scheduleentry_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="schedule",
            name="start_date",
            field=models.DateField(
                default=datetime.date(2026, 7, 10),
                help_text="Date this schedule begins (first day of service)",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="schedule",
            name="frequency",
            field=models.CharField(
                choices=[
                    ("weekly", "Weekly"),
                    ("biweekly", "Bi-weekly (every 2 weeks)"),
                    ("custom", "Custom interval"),
                ],
                default="weekly",
                help_text="How often the schedule repeats",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="schedule",
            name="custom_interval_weeks",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Number of weeks between visits (required when frequency is 'Custom')",
            ),
        ),
        migrations.AddField(
            model_name="schedule",
            name="end_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Optional last date of service. Leave blank for ongoing.",
            ),
        ),
    ]
