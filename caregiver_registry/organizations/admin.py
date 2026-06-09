from django.contrib import admin
from .models import Organization, OrganizationStaff, OrganizationStaffInvite, OrganizationMembership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "primary_admin", "created_at")
    search_fields = ("name", "city")
    readonly_fields = ("created_at",)


@admin.register(OrganizationStaff)
class OrganizationStaffAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    list_filter = ("role", "organization")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("created_at",)


@admin.register(OrganizationStaffInvite)
class OrganizationStaffInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "role", "accepted", "created_at", "expires_at")
    list_filter = ("accepted", "role", "organization")
    search_fields = ("email",)
    readonly_fields = ("token", "created_at")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "status", "created_at")
    list_filter = ("role", "status", "organization")
    search_fields = ("user__email", "user__username", "organization__name")
    readonly_fields = ("created_at", "updated_at")
