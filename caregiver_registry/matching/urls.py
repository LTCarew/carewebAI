from django.urls import path
from . import views

urlpatterns = [
    # ── Caregiver initiates a match with a specific client ────────────────────
    path(
        "match/request/caregiver/<int:client_profile_id>/",
        views.caregiver_request_match,
        name="caregiver_request_match",
    ),

    # ── Client initiates a match with a specific caregiver ────────────────────
    path(
        "match/request/client/<int:caregiver_profile_id>/",
        views.client_request_match,
        name="client_request_match",
    ),

    # ── Staff proposes a match (caregiver_id + client_id in POST body) ────────
    path(
        "match/create/staff/",
        views.staff_create_match,
        name="staff_create_match",
    ),

    # ── Cancel a pending match ────────────────────────────────────────────────
    # NOTE: This MUST come before match_respond (match/<id>/<action>/) so that
    # Django's first-match routing sends /match/<id>/cancel/ to match_cancel
    # and not to match_respond with action="cancel".
    path(
        "match/<int:match_id>/cancel/",
        views.match_cancel,
        name="match_cancel",
    ),

    # ── Approve or decline a match ────────────────────────────────────────────
    path(
        "match/<int:match_id>/<str:action>/",
        views.match_respond,
        name="match_respond",
    ),

    # ── AI-assisted matching ──────────────────────────────────────────────────
    path(
        "match/ai/caregiver/",
        views.ai_match_for_caregiver,
        name="ai_match_caregiver",
    ),
    path(
        "match/ai/client/",
        views.ai_match_for_client,
        name="ai_match_client",
    ),
    path(
        "match/ai/staff/",
        views.ai_match_for_staff,
        name="ai_match_staff",
    ),
]
