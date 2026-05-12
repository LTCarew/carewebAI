from django.contrib import admin

from .models import (
    Caregiver,
    Client,
    Invite
)


@admin.register(Caregiver)
class CaregiverAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "email",
        "status",
        "profile_completed",
    )

    list_filter = (
        "status",
        "profile_completed",
    )

    search_fields = (
        "name",
        "email",
    )


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "email",
        "status",
        "profile_completed",
    )

    list_filter = (
        "status",
        "profile_completed",
    )

    search_fields = (
        "name",
        "email",
    )


admin.site.register(Invite)