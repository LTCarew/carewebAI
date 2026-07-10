"""
Migration: Add permission flags and invited_by FK to OrganizationStaffInvite.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationstaffinvite",
            name="can_approve_applications",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="organizationstaffinvite",
            name="can_invite_staff",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="organizationstaffinvite",
            name="invited_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="staff_invites_sent_by",
                to="accounts.userprofile",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationstaffinvite",
            index=models.Index(fields=["token"], name="org_staff_invite_token_idx"),
        ),
        migrations.AddIndex(
            model_name="organizationstaffinvite",
            index=models.Index(
                fields=["organization", "email"],
                name="org_staff_invite_org_email_idx",
            ),
        ),
    ]
