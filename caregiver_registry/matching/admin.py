from django.contrib import admin
from .models import Tag, Match, Notification


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "label", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "label")
    prepopulated_fields = {"name": ("label",)}
    readonly_fields = ("created_at",)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "caregiver",
        "client",
        "organization",
        "initiated_by",
        "caregiver_status",
        "client_status",
        "staff_status",
        "status",
        "match_score",
        "created_at",
    )
    list_filter = (
        "status",
        "initiated_by",
        "caregiver_status",
        "client_status",
        "staff_status",
        "organization",
    )
    search_fields = (
        "caregiver__user_profile__name",
        "caregiver__user_profile__email",
        "client__user_profile__name",
        "client__user_profile__email",
    )
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("selected_tags",)
    fieldsets = (
        ("Parties", {
            "fields": ("organization", "caregiver", "client", "initiated_by", "initiated_by_user")
        }),
        ("Approval Statuses", {
            "fields": ("caregiver_status", "client_status", "staff_status", "status")
        }),
        ("Scoring & Tags", {
            "fields": ("match_score", "match_details", "selected_tags", "ai_reasoning")
        }),
        ("Notes & Timestamps", {
            "fields": ("notes", "created_at", "updated_at")
        }),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient",
        "notification_type",
        "subject",
        "is_read",
        "created_at",
    )
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("recipient__name", "recipient__email", "subject", "message")
    readonly_fields = ("created_at",)
