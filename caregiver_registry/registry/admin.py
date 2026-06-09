from django.contrib import admin

from .models import (
    CaregiverProfile,
    ClientProfile,
    OrganizationCaregiver,
    OrganizationClient,
    Invite
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


admin.site.register(Invite)
