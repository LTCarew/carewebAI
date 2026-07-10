from django.contrib import admin
from .models import StaffProfile, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "auth_email", "phone", "user", "created_at")
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__email",
        "user__username",
        "phone",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user_profile", "title", "created_at")
    search_fields = (
        "user_profile__user__first_name",
        "user_profile__user__last_name",
        "user_profile__user__email",
        "title",
    )
    readonly_fields = ("created_at", "updated_at")
