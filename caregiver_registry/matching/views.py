"""
Matching views: create matches, respond to matches, AI-assisted suggestions.

All actions that change match state are POST-only.
All views require login. Role-based guards are enforced by services.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from registry.services import get_active_organization, get_user_primary_role
from .models import Match, Tag
from .services import (
    create_match,
    caregiver_respond_to_match,
    client_respond_to_match,
    staff_respond_to_match,
    compute_match_score,
    compute_ai_enhanced_match_score,
    find_best_caregivers_for_client,
    find_best_clients_for_caregiver,
    find_best_pair_for_staff,
)


# ==============================================
# Helper: get requesting user's profile
# ==============================================

def _get_user_profile(request):
    try:
        return request.user.profile
    except Exception:
        return None


# ==============================================
# Stage 3: Create Match — Caregiver Requests Client
# ==============================================

@login_required
def caregiver_request_match(request, client_profile_id):
    """
    Caregiver initiates a match request against a specific client.
    POST only.
    """
    from registry.models import ClientProfile

    if request.method != "POST":
        return redirect("registry_network")

    organization = get_active_organization(request)
    user_role = get_user_primary_role(request.user, organization)

    if user_role != "caregiver":
        messages.error(request, "Only careworkers can initiate match requests from the client registry.")
        return redirect("registry_network")

    try:
        caregiver_profile = request.user.profile.caregiver_profile
    except Exception:
        messages.error(request, "Could not find your careworker profile.")
        return redirect("registry_network")

    client_profile = get_object_or_404(ClientProfile, pk=client_profile_id)

    # Collect selected tag IDs from POST
    tag_ids = request.POST.getlist("tag_ids")

    # Score this pair using ChatGPT-enhanced scoring (falls back to local if unavailable)
    score_result = compute_ai_enhanced_match_score(
        caregiver_profile, client_profile, selected_tag_ids=tag_ids or None
    )

    try:
        match = create_match(
            caregiver=caregiver_profile,
            client=client_profile,
            organization=organization,
            initiated_by="caregiver",
            initiated_by_user=_get_user_profile(request),
            tag_ids=tag_ids or None,
            match_score=score_result["score"],
            match_details=score_result["details"],
            ai_reasoning=score_result["ai_reasoning"],
        )
        messages.success(
            request,
            f"Match request sent to {client_profile.user_profile.display_name}. "
            f"Awaiting client approval."
        )
    except ValueError as e:
        messages.warning(request, str(e))

    return redirect("caregiver_dashboard")


# ==============================================
# Stage 3: Create Match — Client Requests Caregiver
# ==============================================

@login_required
def client_request_match(request, caregiver_profile_id):
    """
    Client initiates a match request against a specific caregiver.
    POST only.
    """
    from registry.models import CaregiverProfile

    if request.method != "POST":
        return redirect("registry_network")

    organization = get_active_organization(request)
    user_role = get_user_primary_role(request.user, organization)

    if user_role != "client":
        messages.error(request, "Only clients can initiate match requests from the careworker registry.")
        return redirect("registry_network")

    try:
        client_profile = request.user.profile.client_profile
    except Exception:
        messages.error(request, "Could not find your profile.")
        return redirect("registry_network")

    caregiver_profile = get_object_or_404(CaregiverProfile, pk=caregiver_profile_id)

    tag_ids = request.POST.getlist("tag_ids")

    # Score this pair using ChatGPT-enhanced scoring (falls back to local if unavailable)
    score_result = compute_ai_enhanced_match_score(
        caregiver_profile, client_profile, selected_tag_ids=tag_ids or None
    )

    try:
        match = create_match(
            caregiver=caregiver_profile,
            client=client_profile,
            organization=organization,
            initiated_by="client",
            initiated_by_user=_get_user_profile(request),
            tag_ids=tag_ids or None,
            match_score=score_result["score"],
            match_details=score_result["details"],
            ai_reasoning=score_result["ai_reasoning"],
        )
        messages.success(
            request,
            f"Match request sent to {caregiver_profile.user_profile.display_name}. "
            f"Awaiting caregiver approval."
        )
    except ValueError as e:
        messages.warning(request, str(e))

    return redirect("client_dashboard")


# ==============================================
# Stage 3: Create Match — Staff Proposes Match
# ==============================================

@login_required
def staff_create_match(request):
    """
    Staff selects a caregiver and a client, optionally selects tags,
    and proposes a match.
    POST only.
    """
    from registry.models import CaregiverProfile, ClientProfile
    from registry.services import user_is_admin_or_staff

    if request.method != "POST":
        return redirect("registry_network")

    if not user_is_admin_or_staff(request.user):
        messages.error(request, "Only staff can propose matches.")
        return redirect("dashboard_redirect")

    organization = get_active_organization(request)
    caregiver_id = request.POST.get("caregiver_id")
    client_id = request.POST.get("client_id")
    tag_ids = request.POST.getlist("tag_ids")
    notes = request.POST.get("notes", "")

    if not caregiver_id or not client_id:
        messages.error(request, "Please select both a careworker and a client.")
        return redirect("registry_network")

    caregiver_profile = get_object_or_404(CaregiverProfile, pk=caregiver_id)
    client_profile = get_object_or_404(ClientProfile, pk=client_id)

    # Score this pair using ChatGPT-enhanced scoring (falls back to local if unavailable)
    score_result = compute_ai_enhanced_match_score(
        caregiver_profile, client_profile, selected_tag_ids=tag_ids or None
    )

    try:
        match = create_match(
            caregiver=caregiver_profile,
            client=client_profile,
            organization=organization,
            initiated_by="staff",
            initiated_by_user=_get_user_profile(request),
            tag_ids=tag_ids or None,
            notes=notes,
            match_score=score_result["score"],
            match_details=score_result["details"],
            ai_reasoning=score_result["ai_reasoning"],
        )
        messages.success(
            request,
            f"Match proposed between {caregiver_profile.user_profile.display_name} and "
            f"{client_profile.user_profile.display_name}. Awaiting caregiver and client approval."
        )
    except ValueError as e:
        messages.warning(request, str(e))

    return redirect("org_dashboard")


# ==============================================
# Stage 3 / 4: Respond to Match (approve/decline)
# ==============================================

@login_required
def match_respond(request, match_id, action):
    """
    Universal match response endpoint.
    Routes to caregiver, client, or staff respond based on requesting user's role.
    Action must be 'approve' or 'decline'. POST only.
    """
    if request.method != "POST":
        return redirect("dashboard_redirect")

    if action not in ("approve", "decline"):
        messages.error(request, "Invalid action.")
        return redirect("dashboard_redirect")

    match = get_object_or_404(Match, pk=match_id)
    organization = get_active_organization(request)
    user_role = get_user_primary_role(request.user, organization)

    try:
        if user_role == "caregiver":
            caregiver_respond_to_match(match, action, request.user)
        elif user_role == "client":
            client_respond_to_match(match, action, request.user)
        elif user_role in ("admin", "staff"):
            messages.error(
                request,
                "Staff can view and track matches but do not approve or decline them. "
                "Only caregivers and clients can respond to matches."
            )
            return redirect("org_dashboard")
        else:
            messages.error(request, "Your role cannot respond to this match.")
            return redirect("dashboard_redirect")

        verb = "approved" if action == "approve" else "declined"
        messages.success(request, f"Match {verb} successfully.")

    except (PermissionError, ValueError) as e:
        messages.error(request, str(e))

    # Redirect back to the appropriate dashboard
    if user_role == "caregiver":
        return redirect("caregiver_dashboard")
    elif user_role == "client":
        return redirect("client_dashboard")
    else:
        return redirect("org_dashboard")


# ==============================================
# Stage 3: Cancel a Match
# ==============================================

@login_required
def match_cancel(request, match_id):
    """
    Cancel a pending match. Staff or the initiating party can cancel.
    POST only.
    """
    if request.method != "POST":
        return redirect("dashboard_redirect")

    match = get_object_or_404(Match, pk=match_id)
    organization = get_active_organization(request)
    user_role = get_user_primary_role(request.user, organization)

    if match.status not in ("pending",):
        messages.error(request, "Only pending matches can be cancelled.")
        return redirect("dashboard_redirect")

    user_profile = _get_user_profile(request)

    # Verify permission: must be staff, or be the caregiver/client on this match
    is_staff = user_role in ("admin", "staff")
    is_caregiver = (
        hasattr(request.user.profile, "caregiver_profile")
        and match.caregiver == request.user.profile.caregiver_profile
    )
    is_client = (
        hasattr(request.user.profile, "client_profile")
        and match.client == request.user.profile.client_profile
    )

    if not (is_staff or is_caregiver or is_client):
        messages.error(request, "You do not have permission to cancel this match.")
        return redirect("dashboard_redirect")

    match.cancel()
    messages.success(request, "Match cancelled.")

    if user_role == "caregiver":
        return redirect("caregiver_dashboard")
    elif user_role == "client":
        return redirect("client_dashboard")
    else:
        return redirect("org_dashboard")


# ==============================================
# Stage 8: AI Assisted Match Views
# ==============================================

@login_required
def ai_match_for_caregiver(request):
    """Redirect to Network Registry where AI matching now lives."""
    return redirect("registry_network")


@login_required
def ai_match_for_client(request):
    """Redirect to Network Registry where AI matching now lives."""
    return redirect("registry_network")


@login_required
def ai_match_for_staff(request):
    """Redirect to Network Registry where AI matching now lives."""
    return redirect("registry_network")
