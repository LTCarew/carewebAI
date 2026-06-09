from django.contrib import admin

from .models import (
    Caregiver,
    Client,
    CaregiverProfile,
    ClientProfile,
    Invite
)


@admin.register(Caregiver)
class CaregiverAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "email",
        "organization",
        "status",
        "profile_completed",
        "created_at",
    )

    list_filter = (
        "status",
        "profile_completed",
        "organization",
    )

    search_fields = (
        "name",
        "email",
    )

    readonly_fields = ("created_at",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "email",
        "organization",
        "status",
        "profile_completed",
        "created_at",
    )

    list_filter = (
        "status",
        "profile_completed",
        "organization",
    )

    search_fields = (
        "name",
        "email",
    )

    readonly_fields = ("created_at",)


@admin.register(CaregiverProfile)
class CaregiverProfileAdmin(admin.ModelAdmin):
    
    list_display = (
        "user",
        "base_zip_code",
        "rate",
        "created_at",
    )
    
    search_fields = (
        "user__email",
        "user__username",
    )
    
    readonly_fields = ("created_at", "updated_at")


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    
    list_display = (
        "user",
        "base_zip_code",
        "created_at",
    )
    
    search_fields = (
        "user__email",
        "user__username",
    )
    
    readonly_fields = ("created_at", "updated_at")


admin.site.register(Invite)
