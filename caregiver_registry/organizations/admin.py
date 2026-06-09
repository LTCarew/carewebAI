from django.contrib import admin
from .models import Organization, OrganizationStaff, OrganizationStaffInvite


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "primary_admin", "created_at")
    search_fields = ("name", "city")
    readonly_fields = ("created_at",)


@admin.register(OrganizationStaff)
class OrganizationStaffAdmin(admin.ModelAdmin):
    list_display = ("staff_profile", "organization", "role", "status", "created_at")
    list_filter = ("role", "status", "organization")
    search_fields = (
        "staff_profile__user_profile__email",
        "staff_profile__user_profile__name",
        "organization__name"
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrganizationStaffInvite)
class OrganizationStaffInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "role", "accepted", "created_at", "expires_at")
    list_filter = ("accepted", "role", "organization")
    search_fields = ("email",)
    readonly_fields = ("token", "created_at")
