from django.contrib import admin

from .models import (
    CaregiverProfile,
    ClientProfile,
    OrganizationCaregiver,
    OrganizationClient,
    SupportCoordinatorProfile,
    ClientCoordinator,
    CoordinatorInvite,
    Invite,
    Schedule,
    ScheduleEntry,
    ScheduleEntryRating,
)


@admin.register(CaregiverProfile)
class CaregiverProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user_profile",
        "base_zip_code",
        "rate",
        "created_at",
    )
    search_fields = (
        "user_profile__name",
        "user_profile__email",
        "base_zip_code",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user_profile",
        "base_zip_code",
        "created_at",
    )
    search_fields = (
        "user_profile__name",
        "user_profile__email",
        "base_zip_code",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrganizationCaregiver)
class OrganizationCaregiverAdmin(admin.ModelAdmin):
    list_display = (
        "caregiver_profile",
        "organization",
        "status",
        "approved_by",
        "created_at",
    )
    list_filter = ("status", "organization")
    search_fields = (
        "caregiver_profile__user_profile__name",
        "caregiver_profile__user_profile__email",
        "organization__name",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrganizationClient)
class OrganizationClientAdmin(admin.ModelAdmin):
    list_display = (
        "client_profile",
        "organization",
        "status",
        "approved_by",
        "created_at",
    )
    list_filter = ("status", "organization")
    search_fields = (
        "client_profile__user_profile__name",
        "client_profile__user_profile__email",
        "organization__name",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(SupportCoordinatorProfile)
class SupportCoordinatorProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user_profile",
        "relationship_to_clients",
        "created_at",
    )
    search_fields = (
        "user_profile__name",
        "user_profile__email",
        "relationship_to_clients",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(ClientCoordinator)
class ClientCoordinatorAdmin(admin.ModelAdmin):
    list_display = (
        "coordinator_profile",
        "client_profile",
        "status",
        "can_edit_profile",
        "can_approve_caregivers",
        "created_at",
    )
    list_filter = ("status", "can_edit_profile", "can_approve_caregivers")
    search_fields = (
        "coordinator_profile__user_profile__name",
        "coordinator_profile__user_profile__email",
        "client_profile__user_profile__name",
        "client_profile__user_profile__email",
    )
    readonly_fields = ("invited_at", "accepted_at", "created_at", "updated_at")


@admin.register(CoordinatorInvite)
class CoordinatorInviteAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "client_profile",
        "invited_by",
        "created_at",
        "expires_at",
        "used_at",
    )
    list_filter = ("created_at", "expires_at")
    search_fields = (
        "email",
        "client_profile__user_profile__name",
        "invited_by__name",
    )
    readonly_fields = ("token", "created_at", "expires_at", "used_at")


admin.site.register(Invite)


class ScheduleEntryInline(admin.TabularInline):
    model = ScheduleEntry
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display  = ("pk", "client", "caregiver", "status", "start_date", "frequency", "end_date", "organization", "created_at")
    list_filter   = ("status", "frequency", "organization")
    search_fields = ("client__user_profile__user__last_name", "caregiver__user_profile__user__last_name")
    readonly_fields = ("created_at", "submitted_at", "cancelled_at")
    inlines = [ScheduleEntryInline]
    fieldsets = (
        ("People", {"fields": ("organization", "client", "caregiver", "support_person", "match", "created_by")}),
        ("Recurrence", {"fields": ("start_date", "frequency", "custom_interval_weeks", "end_date")}),
        ("Status & Notes", {"fields": ("status", "notes")}),
        ("Timestamps", {"fields": ("created_at", "submitted_at", "cancelled_at"), "classes": ("collapse",)}),
    )


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(admin.ModelAdmin):
    list_display = ("schedule", "day_of_week", "start_time", "end_time", "caregiver_status", "support_person_status")
    list_filter = ("caregiver_status", "support_person_status", "day_of_week")
    readonly_fields = ("created_at", "updated_at", "caregiver_reviewed_at", "support_person_reviewed_at")


@admin.register(ScheduleEntryRating)
class ScheduleEntryRatingAdmin(admin.ModelAdmin):
    list_display = (
        "schedule_entry",
        "rater_role",
        "rater_profile",
        "rating_date",
        "care_fit_respect",
        "communication_coordination",
        "reliability_consistency",
        "workload_support_balance",
        "created_at",
    )
    list_filter = ("rater_role", "rating_date")
    search_fields = (
        "schedule_entry__schedule__client__user_profile__user__last_name",
        "schedule_entry__schedule__caregiver__user_profile__user__last_name",
        "rater_profile__user__last_name",
    )
    readonly_fields = ("created_at", "updated_at")
