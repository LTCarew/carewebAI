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

# ==============================================
# Stability Snapshot: Flag for Stabilization Review
# ==============================================

@login_required
def flag_stabilization_review(request, match_id):
    """
    Staff-only POST action: flag an active match for stabilization review.

    Guards:
    - User must be admin/staff (via user_is_admin_or_staff).
    - The match must belong to the user's active organization.
    - Duplicate active flags are silently ignored (idempotent success message).
    """
    from django.utils import timezone as _tz
    from registry.services import user_is_admin_or_staff, get_active_organization

    if request.method != "POST":
        return redirect("org_dashboard")

    if not user_is_admin_or_staff(request.user):
        messages.error(request, "Only staff can flag relationships for stabilization review.")
        return redirect("dashboard_redirect")

    active_org = get_active_organization(request)
    match = get_object_or_404(Match, pk=match_id)

    # Org-scope check: the match must belong to the staff member's active org.
    if match.organization != active_org:
        messages.error(request, "You do not have permission to flag this relationship.")
        return redirect("org_dashboard")

    if match.stabilization_review_requested:
        messages.info(request, "This relationship has already been flagged for stabilization review.")
    else:
        try:
            requester_profile = request.user.profile
        except Exception:
            requester_profile = None

        match.stabilization_review_requested = True
        match.stabilization_review_requested_at = _tz.now()
        match.stabilization_review_requested_by = requester_profile
        match.save(update_fields=[
            "stabilization_review_requested",
            "stabilization_review_requested_at",
            "stabilization_review_requested_by",
            "updated_at",
        ])
        messages.success(
            request,
            f"Relationship between {match.caregiver.user_profile.display_name} "
            f"and {match.client.user_profile.display_name} has been flagged for stabilization review.",
        )

    return redirect("org_dashboard")


@login_required
def unflag_stabilization_review(request, match_id):
    """
    Staff-only POST action: clear the stabilization review flag on a match.

    Mirrors flag_stabilization_review; same guard rules apply.
    """
    from django.utils import timezone as _tz
    from registry.services import user_is_admin_or_staff, get_active_organization

    if request.method != "POST":
        return redirect("match_stability_detail", match_id=match_id)

    if not user_is_admin_or_staff(request.user):
        messages.error(request, "Only staff can manage stabilization review flags.")
        return redirect("dashboard_redirect")

    active_org = get_active_organization(request)
    match = get_object_or_404(Match, pk=match_id)

    if match.organization != active_org:
        messages.error(request, "You do not have permission to modify this relationship.")
        return redirect("org_dashboard")

    if not match.stabilization_review_requested:
        messages.info(request, "This relationship was not flagged.")
    else:
        match.stabilization_review_requested = False
        match.stabilization_review_requested_at = None
        match.stabilization_review_requested_by = None
        match.save(update_fields=[
            "stabilization_review_requested",
            "stabilization_review_requested_at",
            "stabilization_review_requested_by",
            "updated_at",
        ])
        messages.success(
            request,
            f"Stabilization review flag removed for {match.caregiver.user_profile.display_name} "
            f"and {match.client.user_profile.display_name}.",
        )

    return redirect("match_stability_detail", match_id=match_id)


@login_required
def stability_detail(request, match_id):
    """
    Staff-only page: full Stability Snapshot for a single active match.

    Shows:
    - Overall stability status / score / explanation
    - 5 stability signals (schedule_consistency, travel_burden, etc.)
    - Per-entry rating history: for each schedule slot (e.g. Monday 8 AM–12 PM)
      a table of every past session date with client & caregiver scores and notes.
    - Flag / Unflag for Stabilization Review actions.
    """
    from registry.services import user_is_admin_or_staff, get_active_organization
    from .stability import get_stability_snapshot
    from registry.models import ScheduleEntry, ScheduleEntryRating

    if not user_is_admin_or_staff(request.user):
        messages.error(request, "Only staff can view stability detail pages.")
        return redirect("dashboard_redirect")

    active_org = get_active_organization(request)
    match = get_object_or_404(
        Match.objects.select_related(
            "caregiver__user_profile",
            "client__user_profile",
            "organization",
        ),
        pk=match_id,
    )

    if match.organization != active_org:
        messages.error(request, "You do not have permission to view this relationship.")
        return redirect("org_dashboard")

    snapshot = get_stability_snapshot(match)

    # ── Build per-entry rating history ────────────────────────────────────────
    # Find the approved schedule linked to this match (newest if multiple)
    from registry.models import Schedule
    schedule = (
        Schedule.objects.filter(match=match, status="approved")
        .order_by("-created_at")
        .first()
    )

    entry_histories = []
    if schedule:
        entries = (
            ScheduleEntry.objects.filter(schedule=schedule)
            .order_by("day_of_week", "start_time")
        )
        for entry in entries:
            ratings = (
                ScheduleEntryRating.objects.filter(schedule_entry=entry)
                .select_related("rater_profile")
                .order_by("-rating_date", "rater_role")
            )
            # Group by rating_date: date → {client: rating_obj, caregiver: rating_obj}
            from collections import defaultdict
            by_date = defaultdict(dict)
            for r in ratings:
                by_date[r.rating_date][r.rater_role] = r

            # Build sorted list newest-first
            sessions = []
            for session_date in sorted(by_date.keys(), reverse=True):
                raters = by_date[session_date]
                sessions.append({
                    "date": session_date,
                    "client": raters.get("client"),
                    "caregiver": raters.get("caregiver"),
                })

            entry_histories.append({
                "entry": entry,
                "sessions": sessions,
            })

    return render(request, "matching/stability_detail.html", {
        "match": match,
        "snapshot": snapshot,
        "entry_histories": entry_histories,
        "schedule": schedule,
    })


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
