from django.contrib import admin
from .models import StaffProfile, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "user", "created_at")
    search_fields = ("name", "email", "phone", "user__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user_profile", "title", "created_at")
    search_fields = (
        "user_profile__name",
        "user_profile__email",
        "title",
    )
    readonly_fields = ("created_at", "updated_at")
