"""Registry views for application intake, dashboards, and admin review workflow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CaregiverApplicationForm, ClientApplicationForm
from .models import OrganizationCaregiver, OrganizationClient
from .services import (
    approve_caregiver,
    approve_client,
    get_active_organization,
    get_user_primary_role,
    user_is_admin_or_staff,
)


ALLOWED_STATUSES = ["pending", "approved", "rejected", "inactive"]


def _user_is_admin_staff(user):
    """
    Return True when the authenticated user has the admin or staff role.
    """
    return user_is_admin_or_staff(user)


def _redirect_if_not_admin_staff(request):
    """Protect admin workflow pages from non-admin users.

    Returns a redirect response for unauthorized users, otherwise None.
    """
    if _user_is_admin_staff(request.user):
        return None

    messages.error(request, "You do not have permission to access the admin registry workflow.")
    return redirect("dashboard_redirect")


# ==============================================
# Support Coordinator Views
# ==============================================

@login_required
def coordinator_dashboard(request):
    """Dashboard for support coordinators showing their clients."""
    from .services import get_user_coordinator_role, get_coordinator_clients
    
    coordinator_profile = get_user_coordinator_role(request.user)
    
    if not coordinator_profile:
        messages.error(request, "You are not registered as a support coordinator.")
        return redirect("home")
    
    # Get all clients this coordinator supports
    client_relationships = get_coordinator_clients(coordinator_profile)

    # Schedule entries pending this coordinator's approval
    from .models import ScheduleEntry
    pending_schedule_entries = list(
        ScheduleEntry.objects.filter(
            schedule__support_person=coordinator_profile,
            support_person_status="pending",
        ).exclude(
            schedule__status__in=["draft", "cancelled"]
        ).select_related(
            "schedule__client__user_profile",
            "schedule__caregiver__user_profile",
        ).order_by("schedule__submitted_at", "day_of_week", "start_time")
    )

    return render(request, "registry/coordinator_dashboard.html", {
        "coordinator_profile": coordinator_profile,
        "client_relationships": client_relationships,
        "pending_schedule_entries": pending_schedule_entries,
    })


def coordinator_signup(request, token):
    """
    Handle coordinator signup from email invitation.
    """
    from .models import CoordinatorInvite
    from .forms import CoordinatorSignupForm
    
    # Get the invitation
    try:
        invite = CoordinatorInvite.objects.get(token=token)
    except CoordinatorInvite.DoesNotExist:
        messages.error(request, "Invalid invitation link.")
        return redirect("home")
    
    # Check if invitation is valid
    if not invite.is_valid():
        if invite.is_used():
            messages.warning(request, "This invitation has already been used.")
        elif invite.is_expired():
            messages.error(request, "This invitation has expired.")
        return redirect("home")
    
    if request.method == "POST":
        form = CoordinatorSignupForm(request.POST)

        if form.is_valid():
            # save() returns (client_coordinator, user) — use the user directly
            # so we don't need a second DB hit.
            client_coordinator, coordinator_user = form.save(invite)

            messages.success(
                request,
                f"Welcome! You are now a support coordinator for "
                f"{invite.client_profile.user_profile.display_name}. "
                f"You can log in at any time using your email and the password you just set."
            )

            # Log the coordinator in immediately.
            from django.contrib.auth import login
            login(request, coordinator_user, backend='django.contrib.auth.backends.ModelBackend')

            return redirect("coordinator_dashboard")
    else:
        # Pre-fill email from invitation
        form = CoordinatorSignupForm(initial={'email': invite.email})
    
    return render(request, "registry/coordinator_signup.html", {
        "form": form,
        "invite": invite,
    })


@login_required
def coordinator_invite_send(request):
    """
    Client view to send coordinator invitation.
    """
    from .forms import CoordinatorInviteForm
    from .services import send_coordinator_invite
    
    # Check that user is a client
    try:
        client_profile = request.user.profile.client_profile
    except (AttributeError, Exception):
        messages.error(request, "Only clients can invite support coordinators.")
        return redirect("dashboard_redirect")
    
    if request.method == "POST":
        form = CoordinatorInviteForm(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data['email']
            
            try:
                # Send the invitation
                invite = send_coordinator_invite(
                    client_profile=client_profile,
                    email=email,
                    invited_by_user=request.user
                )
                
                messages.success(
                    request,
                    f"Invitation sent to {email}. They will receive an email with signup instructions."
                )
            except Exception as e:
                messages.error(request, f"Error sending invitation: {str(e)}")
            
            return redirect("client_dashboard")
    else:
        form = CoordinatorInviteForm()
    
    return render(request, "registry/coordinator_invite.html", {
        "form": form,
    })


@login_required
def coordinator_permissions_update(request, relationship_id):
    """
    Client view to update a coordinator's permissions.
    """
    from .models import ClientCoordinator
    
    # Get the relationship
    relationship = get_object_or_404(
        ClientCoordinator,
        id=relationship_id,
        client_profile__user_profile__user=request.user
    )
    
    if request.method == "POST":
        # Update permissions from POST data
        relationship.can_edit_profile = request.POST.get('can_edit_profile') == 'on'
        relationship.can_approve_caregivers = request.POST.get('can_approve_caregivers') == 'on'
        relationship.save()
        
        messages.success(
            request,
            f"Permissions updated for {relationship.coordinator_profile.user_profile.display_name}."
        )
    
    return redirect("client_dashboard")


def caregiver_apply(request):
    """Handle caregiver application form submission and rendering."""
    if request.method == "POST":
        form = CaregiverApplicationForm(request.POST)

        if form.is_valid():
            org_caregiver = form.save()

            messages.success(
                request,
                "Application submitted successfully."
            )

            return redirect("application_success")

    else:
        form = CaregiverApplicationForm()

    return render(
        request,
        "registry/caregiver_apply.html",
        {
            "form": form
        }
    )


def client_apply(request):
    """Handle client application form submission and rendering."""
    if request.method == "POST":
        form = ClientApplicationForm(request.POST)

        if form.is_valid():
            org_client = form.save()

            messages.success(
                request,
                "Application submitted successfully."
            )

            return redirect("application_success")
        
    else:
        form = ClientApplicationForm()

    return render(
        request,
        "registry/client_apply.html",
        {
            "form": form
        }
    )


def application_success(request):
    return render(
        request,
        "registry/application_success.html"
    )


def home(request):
    return render(request, "home.html")


@login_required
def dashboard_redirect(request):
    """
    Route users to appropriate dashboard based on their role.
    Checks for support coordinator first, then organization-based roles.
    """
    from .services import get_user_coordinator_role
    
    # Check if user is a support coordinator (takes priority)
    coordinator_profile = get_user_coordinator_role(request.user)
    if coordinator_profile:
        return redirect("coordinator_dashboard")
    
    # Get active organization
    active_org = get_active_organization(request)
    
    if not active_org:
        messages.warning(request, "Your account is not associated with any organization. Please contact support.")
        return redirect("home")
    
    # Get user's role in the active organization
    role = get_user_primary_role(request.user, active_org)
    
    if not role:
        messages.warning(request, "You do not have an active role in this organization. Please contact support.")
        return redirect("home")
    
    # Route based on role
    if role in ["admin", "staff"]:
        return redirect("org_dashboard")
    elif role == "caregiver":
        return redirect("caregiver_dashboard")
    elif role == "client":
        return redirect("client_dashboard")
    
    return redirect("home")


@login_required
def caregiver_dashboard(request):
    """
    Caregiver dashboard showing pending and active matches grouped by state.
    Matches paginated at 10 per group.
    """
    from matching.models import Match

    try:
        caregiver_profile = request.user.profile.caregiver_profile
    except Exception:
        messages.error(request, "Could not load your careworker profile.")
        return redirect("home")

    from django.db.models import Exists, OuterRef

    base_qs = Match.objects.filter(caregiver=caregiver_profile).select_related(
        "client__user_profile",
        "caregiver__user_profile",
        "organization",
    ).prefetch_related("selected_tags")

    def paginate(qs, param, n=10):
        p = Paginator(qs, n)
        return p.get_page(request.GET.get(param, 1))

    # Exclude pending rows where an active match already exists for the same pair
    active_pair_exists_cg = base_qs.filter(
        caregiver_id=OuterRef("caregiver_id"),
        client_id=OuterRef("client_id"),
        status="active",
    )
    pending_qs_cg = (
        base_qs.filter(status="pending")
        .annotate(has_active_pair=Exists(active_pair_exists_cg))
        .filter(has_active_pair=False)
    )

    pending_my_approval   = paginate(pending_qs_cg.filter(caregiver_status="pending"), "p_mine")
    pending_client        = paginate(pending_qs_cg.filter(caregiver_status="approved", client_status="pending"), "p_client")
    active_matches        = paginate(base_qs.filter(status="active"), "p_active")
    declined_matches      = paginate(base_qs.filter(status__in=["declined", "cancelled"]).order_by("-updated_at"), "p_declined")

    # Unread notifications
    unread_notifications = request.user.profile.notifications.filter(is_read=False).order_by("-created_at")[:5]

    # Scheduling: entries pending caregiver approval
    from .models import ScheduleEntry, Schedule
    pending_schedule_entries = list(
        ScheduleEntry.objects.filter(
            schedule__caregiver=caregiver_profile,
            caregiver_status="pending",
        ).exclude(
            schedule__status__in=["draft", "cancelled"]
        ).select_related(
            "schedule__client__user_profile",
            "schedule__caregiver__user_profile",
        ).order_by("schedule__submitted_at", "day_of_week", "start_time")
    )

    # Scheduling: all schedules assigned to this careworker
    my_schedules_qs = Schedule.objects.filter(
        caregiver=caregiver_profile,
    ).select_related(
        "client__user_profile",
        "support_person__user_profile",
    ).prefetch_related("entries").order_by("-created_at")
    my_schedules = Paginator(my_schedules_qs, 10).get_page(request.GET.get("schedules_page", 1))

    # Approved schedules only — shown in the expanded entry view at the top
    approved_schedules = list(
        my_schedules_qs.filter(status="approved")
    )

    return render(request, "registry/caregiver_dashboard.html", {
        "caregiver_profile": caregiver_profile,
        "pending_my_approval": pending_my_approval,
        "pending_client": pending_client,
        "active_matches": active_matches,
        "declined_matches": declined_matches,
        "unread_notifications": unread_notifications,
        "pending_schedule_entries": pending_schedule_entries,
        "my_schedules": my_schedules,
        "approved_schedules": approved_schedules,
    })


@login_required
def client_dashboard(request):
    """
    Client dashboard showing pending and active matches grouped by state.
    Matches paginated at 10 per group.
    """
    from matching.models import Match

    try:
        client_profile = request.user.profile.client_profile
    except Exception:
        messages.error(request, "Could not load your profile.")
        return redirect("home")

    from django.db.models import Exists, OuterRef

    base_qs = Match.objects.filter(client=client_profile).select_related(
        "client__user_profile",
        "caregiver__user_profile",
        "organization",
    ).prefetch_related("selected_tags")

    def paginate(qs, param, n=10):
        p = Paginator(qs, n)
        return p.get_page(request.GET.get(param, 1))

    # Exclude pending rows where an active match already exists for the same pair
    active_pair_exists_cl = base_qs.filter(
        caregiver_id=OuterRef("caregiver_id"),
        client_id=OuterRef("client_id"),
        status="active",
    )
    pending_qs_cl = (
        base_qs.filter(status="pending")
        .annotate(has_active_pair=Exists(active_pair_exists_cl))
        .filter(has_active_pair=False)
    )

    pending_my_approval   = paginate(pending_qs_cl.filter(client_status="pending"), "p_mine")
    pending_caregiver     = paginate(pending_qs_cl.filter(client_status="approved", caregiver_status="pending"), "p_cg")
    active_matches        = paginate(base_qs.filter(status="active"), "p_active")
    declined_matches      = paginate(base_qs.filter(status__in=["declined", "cancelled"]).order_by("-updated_at"), "p_declined")

    # Unread notifications
    unread_notifications = request.user.profile.notifications.filter(is_read=False).order_by("-created_at")[:5]

    # Coordinator support
    from .services import get_client_coordinators
    coordinators_qs = get_client_coordinators(client_profile)
    coordinators = Paginator(coordinators_qs, 10).get_page(request.GET.get("coordinators_page", 1))

    # Scheduling: client's schedules
    from .models import Schedule
    my_schedules_qs = Schedule.objects.filter(
        client=client_profile,
    ).select_related(
        "caregiver__user_profile",
        "support_person__user_profile",
    ).prefetch_related("entries").order_by("-created_at")
    my_schedules = Paginator(my_schedules_qs, 10).get_page(request.GET.get("schedules_page", 1))

    return render(request, "registry/client_dashboard.html", {
        "client_profile": client_profile,
        "pending_my_approval": pending_my_approval,
        "pending_caregiver": pending_caregiver,
        "active_matches": active_matches,
        "declined_matches": declined_matches,
        "unread_notifications": unread_notifications,
        "coordinators": coordinators,
        "my_schedules": my_schedules,
    })


@login_required
def registry_network(request):
    """
    Unified registry matching page with role-based visibility.

    - Caregiver: selects tags, sees scored client matches from their network.
    - Client:    selects tags, sees scored caregiver matches from their network.
    - Staff:     selects match direction (caregiver→clients or client→caregivers),
                 picks one person, selects tags, sees scored results.

    Nothing is displayed until criteria are submitted.
    """
    from matching.models import Tag
    from matching.services import (
        find_best_clients_for_caregiver,
        find_best_caregivers_for_client,
    )
    from registry.models import CaregiverProfile, ClientProfile

    # Get active organization
    organization = get_active_organization(request)

    if not organization:
        messages.warning(request, "Your account is not linked to an organization yet.")
        return redirect("dashboard_redirect")

    user_role = get_user_primary_role(request.user, organization)

    if not user_role:
        messages.warning(request, "You do not have an active role in this organization.")
        return redirect("dashboard_redirect")

    all_tags = Tag.objects.filter(is_active=True)
    tag_ids = request.GET.getlist("tag_ids")
    ai_mode = request.GET.get("ai") == "1"  # True when user clicked "✨ AI Match"
    match_results = None       # Only populated after the user submits criteria
    match_direction = None     # "find_clients" or "find_caregivers"

    # ── Caregiver: they are the caregiver; select tags to find matching clients ──
    if user_role == "caregiver":
        try:
            caregiver_profile = request.user.profile.caregiver_profile
        except Exception:
            messages.error(request, "Could not load your careworker profile.")
            return redirect("dashboard_redirect")

        # Get all orgs this caregiver is approved in (their network scope)
        caregiver_org_ids = OrganizationCaregiver.objects.filter(
            caregiver_profile=caregiver_profile,
            status="approved",
        ).values_list("organization_id", flat=True)

        # Build a queryset of org_clients for the active organization scope
        org_clients_qs = OrganizationClient.objects.filter(
            organization_id__in=caregiver_org_ids,
            status="approved",
        ).select_related("client_profile__user_profile", "organization").distinct()

        match_direction = "find_clients"

        if tag_ids or ai_mode:
            # Score all eligible clients against this caregiver in their orgs
            from matching.services import find_best_clients_for_caregiver as _find
            raw_results = []
            seen_client_ids = set()
            for org_id in caregiver_org_ids:
                from organizations.models import Organization
                try:
                    org_obj = Organization.objects.get(pk=org_id)
                except Organization.DoesNotExist:
                    continue
                for r in _find(caregiver_profile, org_obj, limit=200, tag_ids=tag_ids or None):
                    if r["client"].pk not in seen_client_ids:
                        seen_client_ids.add(r["client"].pk)
                        raw_results.append(r)
            raw_results.sort(key=lambda x: x["score"], reverse=True)
            all_results = raw_results
            match_results = Paginator(all_results, 10).get_page(request.GET.get("page", 1))

        return render(request, "registry/network_registry.html", {
            "user_role": user_role,
            "is_admin_staff": False,
            "organization_name": organization.name,
            "all_tags": all_tags,
            "selected_tag_ids": [int(t) for t in tag_ids],
            "match_direction": match_direction,
            "match_results": match_results,
            "caregiver_profile": caregiver_profile,
        })

    # ── Client: they are the client; select tags to find matching caregivers ──
    elif user_role == "client":
        try:
            client_profile = request.user.profile.client_profile
        except Exception:
            messages.error(request, "Could not load your profile.")
            return redirect("dashboard_redirect")

        client_org_ids = OrganizationClient.objects.filter(
            client_profile=client_profile,
            status="approved",
        ).values_list("organization_id", flat=True)

        match_direction = "find_caregivers"

        if tag_ids or ai_mode:
            from matching.services import find_best_caregivers_for_client as _find
            raw_results = []
            seen_cg_ids = set()
            for org_id in client_org_ids:
                from organizations.models import Organization
                try:
                    org_obj = Organization.objects.get(pk=org_id)
                except Organization.DoesNotExist:
                    continue
                for r in _find(client_profile, org_obj, limit=200, tag_ids=tag_ids):
                    if r["caregiver"].pk not in seen_cg_ids:
                        seen_cg_ids.add(r["caregiver"].pk)
                        raw_results.append(r)
            raw_results.sort(key=lambda x: x["score"], reverse=True)
            match_results = Paginator(raw_results, 10).get_page(request.GET.get("page", 1))

        return render(request, "registry/network_registry.html", {
            "user_role": user_role,
            "is_admin_staff": False,
            "organization_name": organization.name,
            "all_tags": all_tags,
            "selected_tag_ids": [int(t) for t in tag_ids],
            "match_direction": match_direction,
            "match_results": match_results,
            "client_profile": client_profile,
        })

    # ── Staff/Admin: toggle direction, pick one person, then see scored results ──
    elif user_role in ["admin", "staff"]:
        # Direction toggle: 'find_clients' = staff picks a caregiver then sees matching clients
        #                   'find_caregivers' = staff picks a client then sees matching caregivers
        match_direction = request.GET.get("match_type", "find_clients")
        if match_direction not in ("find_clients", "find_caregivers"):
            match_direction = "find_clients"

        # Load org members for the dropdowns
        org_caregivers_qs = OrganizationCaregiver.objects.filter(
            organization=organization,
            status="approved",
        ).select_related("caregiver_profile__user_profile__user").order_by(
            "caregiver_profile__user_profile__user__last_name",
            "caregiver_profile__user_profile__user__first_name",
        )

        org_clients_qs = OrganizationClient.objects.filter(
            organization=organization,
            status="approved",
        ).select_related("client_profile__user_profile__user").order_by(
            "client_profile__user_profile__user__last_name",
            "client_profile__user_profile__user__first_name",
        )

        selected_caregiver = None
        selected_client = None

        if match_direction == "find_clients":
            caregiver_id = request.GET.get("caregiver_id")
            if caregiver_id:
                try:
                    selected_caregiver = CaregiverProfile.objects.get(pk=caregiver_id)
                except CaregiverProfile.DoesNotExist:
                    pass

            if selected_caregiver and (tag_ids or ai_mode):
                raw_results = find_best_clients_for_caregiver(
                    selected_caregiver, organization, limit=200, tag_ids=tag_ids or None
                )
                match_results = Paginator(raw_results, 10).get_page(request.GET.get("page", 1))

        else:  # find_caregivers
            client_id = request.GET.get("client_id")
            if client_id:
                try:
                    selected_client = ClientProfile.objects.get(pk=client_id)
                except ClientProfile.DoesNotExist:
                    pass

            if selected_client and (tag_ids or ai_mode):
                raw_results = find_best_caregivers_for_client(
                    selected_client, organization, limit=200, tag_ids=tag_ids or None
                )
                match_results = Paginator(raw_results, 10).get_page(request.GET.get("page", 1))

        return render(request, "registry/network_registry.html", {
            "user_role": user_role,
            "is_admin_staff": True,
            "organization_name": organization.name,
            "all_tags": all_tags,
            "selected_tag_ids": [int(t) for t in tag_ids],
            "match_direction": match_direction,
            "match_results": match_results,
            "org_caregivers": org_caregivers_qs,
            "org_clients": org_clients_qs,
            "selected_caregiver": selected_caregiver,
            "selected_client": selected_client,
        })

    else:
        messages.error(request, "Unsupported account role for registry access.")
        return redirect("dashboard_redirect")


@login_required
def org_dashboard(request):
    """
    Organization dashboard for staff and admin roles.
    Shows ALL profiles with status for this organization.
    """
    from .models import CaregiverProfile, ClientProfile
    
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    # Get active organization
    active_org = get_active_organization(request)
    organization_name = active_org.name if active_org else ""
    
    # Get user's role in this organization
    user_role = get_user_primary_role(request.user, active_org) if active_org else None
    role_display = "Staff Admin" if user_role in ("admin", "staff") else (user_role.title() if user_role else "Staff Admin")
    
    # Get ALL caregiver and client profiles
    all_caregivers = CaregiverProfile.objects.select_related('user_profile').all()
    all_clients = ClientProfile.objects.select_related('user_profile').all()
    
    # Get existing relationships for this org
    if active_org:
        caregiver_relationships = {
            rel.caregiver_profile_id: rel 
            for rel in OrganizationCaregiver.objects.filter(organization=active_org)
        }
        client_relationships = {
            rel.client_profile_id: rel 
            for rel in OrganizationClient.objects.filter(organization=active_org)
        }
    else:
        caregiver_relationships = {}
        client_relationships = {}
    
    # Annotate profiles with org-specific status
    caregiver_data = []
    for caregiver in all_caregivers:
        rel = caregiver_relationships.get(caregiver.id)
        caregiver_data.append({
            'pk': rel.pk if rel else None,
            'profile_id': caregiver.id,
            'name': caregiver.user_profile.display_name,
            'email': caregiver.user_profile.auth_email,
            'phone': caregiver.user_profile.phone or '',
            'status': rel.status if rel else 'pending',
            'relationship': rel
        })
    
    client_data = []
    for client in all_clients:
        rel = client_relationships.get(client.id)
        client_data.append({
            'pk': rel.pk if rel else None,
            'profile_id': client.id,
            'name': client.user_profile.display_name,
            'email': client.user_profile.auth_email,
            'phone': client.user_profile.phone or '',
            'status': rel.status if rel else 'pending',
            'relationship': rel
        })
    
    # Count by status
    pending_caregivers = sum(1 for c in caregiver_data if c['status'] == 'pending')
    approved_caregivers = sum(1 for c in caregiver_data if c['status'] == 'approved')
    pending_clients = sum(1 for c in client_data if c['status'] == 'pending')
    approved_clients = sum(1 for c in client_data if c['status'] == 'approved')
    
    full_name = request.user.get_full_name().strip() or request.user.username

    # ── Match context for Stage 4 / 6 ─────────────────────────────────────
    from matching.models import Match

    def paginate(qs, param, n=10):
        p = Paginator(qs, n)
        return p.get_page(request.GET.get(param, 1))

    if active_org:
        from django.db.models import Exists, OuterRef

        match_base = Match.objects.filter(organization=active_org).select_related(
            "caregiver__user_profile", "client__user_profile", "organization"
        ).prefetch_related("selected_tags")

        # Subquery: does an active match already exist for this caregiver/client pair?
        active_pair_exists = match_base.filter(
            caregiver_id=OuterRef("caregiver_id"),
            client_id=OuterRef("client_id"),
            status="active",
        )

        # Pending matches must NOT have a corresponding active match for the same pair
        pending_qs = (
            match_base.filter(status="pending")
            .annotate(has_active_pair=Exists(active_pair_exists))
            .filter(has_active_pair=False)
        )

        match_inquiries           = paginate(pending_qs, "p_inq")
        pending_caregiver_matches = paginate(pending_qs.filter(caregiver_status="pending"), "p_cg")
        pending_client_matches    = paginate(pending_qs.filter(client_status="pending"), "p_cl")
        active_matches            = paginate(match_base.filter(status="active"), "p_act")
        declined_matches          = paginate(match_base.filter(status__in=["declined", "cancelled"]), "p_dec")
    else:
        match_inquiries = pending_caregiver_matches = pending_client_matches = active_matches = declined_matches = None

    selected_view = request.GET.get("view", "caregivers")
    if selected_view not in ("caregivers", "clients", "staff"):
        selected_view = "caregivers"

    # Paginate the caregiver and client application lists
    caregivers_page = Paginator(caregiver_data, 10).get_page(request.GET.get("caregivers_page", 1))
    clients_page = Paginator(client_data, 10).get_page(request.GET.get("clients_page", 1))

    # Scheduling oversight
    from .models import Schedule
    all_schedules_qs = Schedule.objects.filter(
        organization=active_org,
    ).select_related(
        "client__user_profile",
        "caregiver__user_profile",
        "support_person__user_profile",
    ).prefetch_related("entries").order_by("-created_at") if active_org else Schedule.objects.none()
    all_schedules = Paginator(all_schedules_qs, 10).get_page(request.GET.get("schedules_page", 1))

    # ── Staff members & pending invites ──────────────────────────────────────
    from organizations.models import OrganizationStaff, OrganizationStaffInvite
    can_invite_staff = False
    staff_members_page = None
    pending_invites_page = None

    if active_org:
        try:
            my_org_staff = OrganizationStaff.objects.get(
                staff_profile=request.user.profile.staff_profile,
                organization=active_org,
                status="active",
            )
            can_invite_staff = (my_org_staff.role == "admin" or my_org_staff.can_invite_staff)
        except (OrganizationStaff.DoesNotExist, AttributeError):
            pass

        staff_qs = OrganizationStaff.objects.filter(
            organization=active_org,
            status="active",
        ).select_related(
            "staff_profile__user_profile__user",
        ).order_by(
            "staff_profile__user_profile__user__last_name",
            "staff_profile__user_profile__user__first_name",
        )
        staff_members_page = Paginator(staff_qs, 10).get_page(request.GET.get("staff_page", 1))

        invites_qs = OrganizationStaffInvite.objects.filter(
            organization=active_org,
            accepted=False,
        ).order_by("-created_at")
        pending_invites_page = Paginator(invites_qs, 10).get_page(request.GET.get("invites_page", 1))

    return render(request, "registry/org_dashboard.html", {
        "caregivers": caregivers_page,
        "clients": clients_page,
        "pending_caregivers": pending_caregivers,
        "pending_clients": pending_clients,
        "approved_caregivers": approved_caregivers,
        "approved_clients": approved_clients,
        "user_display_name": full_name,
        "organization_name": organization_name,
        "user_role": role_display,
        "selected_view": selected_view,
        # Match tables
        "match_inquiries": match_inquiries,
        "pending_caregiver_matches": pending_caregiver_matches,
        "pending_client_matches": pending_client_matches,
        "active_matches": active_matches,
        "declined_matches": declined_matches,
        # Schedule oversight
        "all_schedules": all_schedules,
        # Staff members & invites
        "staff_members": staff_members_page,
        "pending_invites": pending_invites_page,
        "can_invite_staff": can_invite_staff,
    })


@login_required
def caregiver_detail(request, pk):
    """
    Display caregiver application/profile details.

    Access rules:
    - Admin / staff: full access; pk may be OrganizationCaregiver.pk or
      CaregiverProfile.pk (relationship created if missing).
    - Client: read-only view, allowed only when the client and caregiver
      share at least one common organisation.  pk is treated as
      CaregiverProfile.pk.  No new relationship is created.
    """
    from .models import CaregiverProfile, ClientProfile

    is_admin_staff = _user_is_admin_staff(request.user)

    # ── Admin / staff path ────────────────────────────────────────────────
    if is_admin_staff:
        active_org = get_active_organization(request)

        try:
            org_caregiver = OrganizationCaregiver.objects.select_related(
                'caregiver_profile__user_profile',
                'organization'
            ).get(pk=pk)

            if org_caregiver.organization != active_org:
                raise OrganizationCaregiver.DoesNotExist

        except OrganizationCaregiver.DoesNotExist:
            caregiver_profile = get_object_or_404(CaregiverProfile, pk=pk)
            org_caregiver, _ = OrganizationCaregiver.objects.get_or_create(
                organization=active_org,
                caregiver_profile=caregiver_profile,
                defaults={'status': 'pending'}
            )

        return render(request, "registry/caregiver_detail.html", {
            "org_caregiver": org_caregiver,
            "viewer_role": "staff",
        })

    # ── Client path (read-only, shared-org required) ──────────────────────
    try:
        viewer_client = ClientProfile.objects.get(user_profile__user=request.user)
    except ClientProfile.DoesNotExist:
        messages.error(request, "You don't have permission to view that profile.")
        return redirect("dashboard_redirect")

    caregiver_profile = get_object_or_404(CaregiverProfile, pk=pk)

    # Find any OrganizationCaregiver row for this caregiver that is linked
    # to an org the viewer's client also belongs to.
    client_org_ids = OrganizationClient.objects.filter(
        client_profile=viewer_client
    ).values_list('organization_id', flat=True)

    org_caregiver = OrganizationCaregiver.objects.filter(
        caregiver_profile=caregiver_profile,
        organization_id__in=client_org_ids,
    ).select_related('caregiver_profile__user_profile', 'organization').first()

    if not org_caregiver:
        messages.error(request, "You don't have access to that careworker's profile.")
        return redirect("client_dashboard")

    return render(request, "registry/caregiver_detail.html", {
        "org_caregiver": org_caregiver,
        "viewer_role": "client",
    })


@login_required
def client_detail(request, pk):
    """
    Display client application/profile details.

    Access rules:
    - Admin / staff: full access; pk may be OrganizationClient.pk or
      ClientProfile.pk (relationship created if missing).
    - Caregiver: read-only view, allowed only when the caregiver and client
      share at least one common organisation.  pk is treated as
      ClientProfile.pk.  No new relationship is created.
    """
    from .models import ClientProfile, CaregiverProfile

    is_admin_staff = _user_is_admin_staff(request.user)

    # ── Admin / staff path ────────────────────────────────────────────────
    if is_admin_staff:
        active_org = get_active_organization(request)

        try:
            org_client = OrganizationClient.objects.select_related(
                'client_profile__user_profile',
                'organization'
            ).get(pk=pk)

            if org_client.organization != active_org:
                raise OrganizationClient.DoesNotExist

        except OrganizationClient.DoesNotExist:
            client_profile = get_object_or_404(ClientProfile, pk=pk)
            org_client, _ = OrganizationClient.objects.get_or_create(
                organization=active_org,
                client_profile=client_profile,
                defaults={'status': 'pending'}
            )

        return render(request, "registry/client_detail.html", {
            "org_client": org_client,
            "viewer_role": "staff",
        })

    # ── Caregiver path (read-only, shared-org required) ───────────────────
    try:
        viewer_caregiver = CaregiverProfile.objects.get(user_profile__user=request.user)
    except CaregiverProfile.DoesNotExist:
        messages.error(request, "You don't have permission to view that profile.")
        return redirect("dashboard_redirect")

    client_profile = get_object_or_404(ClientProfile, pk=pk)

    # Find any OrganizationClient row for this client that is linked to an
    # org the viewer's caregiver also belongs to.
    caregiver_org_ids = OrganizationCaregiver.objects.filter(
        caregiver_profile=viewer_caregiver
    ).values_list('organization_id', flat=True)

    org_client = OrganizationClient.objects.filter(
        client_profile=client_profile,
        organization_id__in=caregiver_org_ids,
    ).select_related('client_profile__user_profile', 'organization').first()

    if not org_client:
        messages.error(request, "You don't have access to that person's profile.")
        return redirect("caregiver_dashboard")

    return render(request, "registry/client_detail.html", {
        "org_client": org_client,
        "viewer_role": "caregiver",
    })


@login_required
def update_caregiver_status(request, pk, status):
    """Update caregiver application status."""
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    org_caregiver = get_object_or_404(OrganizationCaregiver, pk=pk)

    # Status updates are state-changing operations, so only allow POST.
    if request.method != "POST":
        return redirect("caregiver_detail", pk=pk)

    if status not in ALLOWED_STATUSES:
        messages.error(request, "Invalid status.")
        return redirect("caregiver_detail", pk=pk)

    # If approving, use the approval service
    if status == "approved" and org_caregiver.status != "approved":
        try:
            approve_caregiver(org_caregiver, request.user)
            caregiver_name = org_caregiver.caregiver_profile.user_profile.display_name
            messages.success(
                request,
                f"{caregiver_name} was approved."
            )
        except Exception as e:
            messages.error(request, f"Error approving application: {str(e)}")
            return redirect("caregiver_detail", pk=pk)
    else:
        # For rejected or other status changes, just update the status
        org_caregiver.status = status
        org_caregiver.save()
        caregiver_name = org_caregiver.caregiver_profile.user_profile.display_name
        messages.success(request, f"{caregiver_name} was marked as {status}.")

    return redirect("caregiver_detail", pk=pk)


@login_required
def update_client_status(request, pk, status):
    """Update client application status."""
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    org_client = get_object_or_404(OrganizationClient, pk=pk)

    # Status updates are state-changing operations, so only allow POST.
    if request.method != "POST":
        return redirect("client_detail", pk=pk)

    if status not in ALLOWED_STATUSES:
        messages.error(request, "Invalid status.")
        return redirect("client_detail", pk=pk)

    # If approving, use the approval service
    if status == "approved" and org_client.status != "approved":
        try:
            approve_client(org_client, request.user)
            client_name = org_client.client_profile.user_profile.display_name
            messages.success(
                request,
                f"{client_name} was approved."
            )
        except Exception as e:
            messages.error(request, f"Error approving application: {str(e)}")
            return redirect("client_detail", pk=pk)
    else:
        # For rejected or other status changes, just update the status
        org_client.status = status
        org_client.save()
        client_name = org_client.client_profile.user_profile.display_name
        messages.success(request, f"{client_name} was marked as {status}.")

    return redirect("client_detail", pk=pk)


@login_required
def update_caregiver_status_by_profile(request, profile_id, status):
    """
    Approve/reject/pend a caregiver by their CaregiverProfile pk.
    Creates an OrganizationCaregiver relationship if one doesn't exist yet,
    then updates the status.  POST only.
    """
    from .models import CaregiverProfile

    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    if request.method != "POST":
        return redirect("org_dashboard")

    if status not in ALLOWED_STATUSES:
        messages.error(request, "Invalid status.")
        return redirect("org_dashboard")

    active_org = get_active_organization(request)
    caregiver_profile = get_object_or_404(CaregiverProfile, pk=profile_id)

    org_caregiver, _ = OrganizationCaregiver.objects.get_or_create(
        organization=active_org,
        caregiver_profile=caregiver_profile,
        defaults={"status": "pending"},
    )

    if status == "approved" and org_caregiver.status != "approved":
        try:
            approve_caregiver(org_caregiver, request.user)
            messages.success(request, f"{caregiver_profile.user_profile.display_name} was approved.")
        except Exception as e:
            messages.error(request, f"Error approving: {str(e)}")
    else:
        org_caregiver.status = status
        org_caregiver.save()
        messages.success(request, f"{caregiver_profile.user_profile.display_name} was marked as {status}.")

    return redirect("org_dashboard")


@login_required
def update_client_status_by_profile(request, profile_id, status):
    """
    Approve/reject/pend a client by their ClientProfile pk.
    Creates an OrganizationClient relationship if one doesn't exist yet,
    then updates the status.  POST only.
    """
    from .models import ClientProfile

    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    if request.method != "POST":
        return redirect("org_dashboard")

    if status not in ALLOWED_STATUSES:
        messages.error(request, "Invalid status.")
        return redirect("org_dashboard")

    active_org = get_active_organization(request)
    client_profile = get_object_or_404(ClientProfile, pk=profile_id)

    org_client, _ = OrganizationClient.objects.get_or_create(
        organization=active_org,
        client_profile=client_profile,
        defaults={"status": "pending"},
    )

    if status == "approved" and org_client.status != "approved":
        try:
            approve_client(org_client, request.user)
            messages.success(request, f"{client_profile.user_profile.display_name} was approved.")
        except Exception as e:
            messages.error(request, f"Error approving: {str(e)}")
    else:
        org_client.status = status
        org_client.save()
        messages.success(request, f"{client_profile.user_profile.display_name} was marked as {status}.")

    return redirect("org_dashboard")


@login_required
def switch_organization(request, org_id):
    """Switch the active organization in the user's session."""
    from .services import get_user_organizations
    
    user_orgs = get_user_organizations(request.user)
    
    if user_orgs.filter(id=org_id).exists():
        request.session['active_organization_id'] = org_id
        messages.success(request, "Organization switched successfully.")
    else:
        messages.error(request, "You do not have access to that organization.")
    
    return redirect("dashboard_redirect")


# ==============================================
# Pool Browsing Views (for adding to organization)
# ==============================================

@login_required
def caregiver_pool(request):
    """
    Show caregivers not yet added to this organization.
    Admins can browse and add them.
    """
    from .models import CaregiverProfile  # local import to avoid circular deps

    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    # Get active organization
    active_org = get_active_organization(request)

    if not active_org:
        messages.error(request, "No active organization found.")
        return redirect("org_dashboard")

    # Get all caregiver profiles (ordered for consistent pagination)
    all_caregivers = CaregiverProfile.objects.select_related('user_profile').order_by(
        'user_profile__user__last_name', 'user_profile__user__first_name'
    )

    # Exclude those already in this organization
    existing_ids = OrganizationCaregiver.objects.filter(
        organization=active_org
    ).values_list('caregiver_profile_id', flat=True)

    available_caregivers = all_caregivers.exclude(id__in=existing_ids)

    caregivers_page = Paginator(available_caregivers, 10).get_page(request.GET.get("caregivers_page", 1))

    return render(request, "registry/caregiver_pool.html", {
        "caregivers": caregivers_page,
        "organization": active_org,
    })


@login_required
def client_pool(request):
    """
    Show clients not yet added to this organization.
    Admins can browse and add them.
    """
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect
    
    # Get active organization
    active_org = get_active_organization(request)
    
    if not active_org:
        messages.error(request, "No active organization found.")
        return redirect("org_dashboard")
    
    # Get all client profiles
    from .models import ClientProfile
    all_clients = ClientProfile.objects.select_related('user_profile').all()
    
    # Exclude those already in this organization
    existing_ids = OrganizationClient.objects.filter(
        organization=active_org
    ).values_list('client_profile_id', flat=True)
    
    available_clients = all_clients.exclude(id__in=existing_ids)

    clients_page = Paginator(available_clients, 10).get_page(request.GET.get("clients_page", 1))

    return render(request, "registry/client_pool.html", {
        "clients": clients_page,
        "organization": active_org,
    })


@login_required
def add_caregiver_to_org(request, profile_id):
    """
    Add a caregiver from the pool to the organization (pending status).
    """
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect
    
    # Get active organization
    active_org = get_active_organization(request)
    
    if not active_org:
        messages.error(request, "No active organization found.")
        return redirect("org_dashboard")
    
    # Get the caregiver profile
    from .models import CaregiverProfile
    caregiver_profile = get_object_or_404(CaregiverProfile, pk=profile_id)
    
    # Create the relationship
    org_caregiver, created = OrganizationCaregiver.objects.get_or_create(
        organization=active_org,
        caregiver_profile=caregiver_profile,
        defaults={'status': 'pending'}
    )
    
    if created:
        messages.success(
            request,
            f"{caregiver_profile.user_profile.display_name} added to your organization for review."
        )
    else:
        messages.info(request, f"{caregiver_profile.user_profile.display_name} is already in your organization.")
    
    return redirect("org_dashboard")


@login_required
def add_client_to_org(request, profile_id):
    """
    Add a client from the pool to the organization (pending status).
    """
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect
    
    # Get active organization
    active_org = get_active_organization(request)
    
    if not active_org:
        messages.error(request, "No active organization found.")
        return redirect("org_dashboard")
    
    # Get the client profile
    from .models import ClientProfile
    client_profile = get_object_or_404(ClientProfile, pk=profile_id)
    
    # Create the relationship
    org_client, created = OrganizationClient.objects.get_or_create(
        organization=active_org,
        client_profile=client_profile,
        defaults={'status': 'pending'}
    )
    
    if created:
        messages.success(
            request,
        f"{client_profile.user_profile.display_name} added to your organization for review."
        )
    else:
        messages.info(request, f"{client_profile.user_profile.display_name} is already in your organization.")
    
    return redirect("org_dashboard")


# ==============================================
# Scheduling Views
# ==============================================

@login_required
def schedule_list(request):
    """
    Redirect to the role-appropriate dashboard which now shows schedules.
    """
    return redirect("dashboard_redirect")


@login_required
def schedule_create(request):
    """
    Client creates a new draft schedule.
    Only clients may create schedules.
    """
    from .models import ClientProfile, Schedule, ScheduleEntry
    from .forms import ScheduleForm, ScheduleEntryForm
    from django.forms import formset_factory

    try:
        client_profile = request.user.profile.client_profile
    except Exception:
        messages.error(request, "Only clients can create schedules.")
        return redirect("dashboard_redirect")

    organization = get_active_organization(request)
    if not organization:
        messages.error(request, "No active organization found.")
        return redirect("dashboard_redirect")

    EntryFormSet = formset_factory(ScheduleEntryForm, extra=1, can_delete=False)

    if request.method == "POST":
        form = ScheduleForm(request.POST, client_profile=client_profile)
        formset = EntryFormSet(request.POST, prefix="entries")

        if form.is_valid() and formset.is_valid():
            # Validate at least one entry
            valid_entries = [
                f for f in formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if not valid_entries:
                messages.error(request, "Please add at least one day/time entry.")
            else:
                matched = form.cleaned_data["match"]
                schedule = Schedule.objects.create(
                    organization=organization,
                    client=client_profile,
                    caregiver=matched.caregiver,
                    support_person=form.cleaned_data.get("support_person"),
                    match=matched,
                    created_by=request.user.profile,
                    status="draft",
                    notes=form.cleaned_data.get("notes", ""),
                    start_date=form.cleaned_data["start_date"],
                    frequency=form.cleaned_data["frequency"],
                    custom_interval_weeks=form.cleaned_data.get("custom_interval_weeks"),
                    end_date=form.cleaned_data.get("end_date"),
                )
                for entry_form in valid_entries:
                    ScheduleEntry.objects.create(
                        schedule=schedule,
                        day_of_week=entry_form.cleaned_data["day_of_week"],
                        start_time=entry_form.cleaned_data["start_time"],
                        end_time=entry_form.cleaned_data["end_time"],
                    )
                messages.success(request, "Draft schedule created. You can edit and submit it when ready.")
                return redirect("schedule_detail", pk=schedule.pk)
    else:
        form = ScheduleForm(client_profile=client_profile)
        formset = EntryFormSet(prefix="entries")

    return render(request, "registry/schedule_form.html", {
        "form": form,
        "formset": formset,
        "action": "create",
        "page_title": "Create Schedule",
    })


@login_required
def schedule_detail(request, pk):
    """
    View a schedule. Accessible to the involved client, caregiver,
    support person, and staff/admin.
    """
    from .models import Schedule

    schedule = get_object_or_404(
        Schedule.objects.select_related(
            "client__user_profile",
            "caregiver__user_profile",
            "support_person__user_profile",
            "organization",
            "created_by",
        ).prefetch_related("entries"),
        pk=pk,
    )

    user_profile = request.user.profile
    is_client = (
        hasattr(user_profile, "client_profile")
        and user_profile.client_profile == schedule.client
    )
    is_caregiver = (
        hasattr(user_profile, "caregiver_profile")
        and user_profile.caregiver_profile == schedule.caregiver
    )
    is_support = (
        schedule.support_person is not None
        and hasattr(user_profile, "support_coordinator_profile")
        and user_profile.support_coordinator_profile == schedule.support_person
    )
    is_staff = _is_admin_or_staff(request)

    if not (is_client or is_caregiver or is_support or is_staff):
        messages.error(request, "You do not have permission to view this schedule.")
        return redirect("dashboard_redirect")

    return render(request, "registry/schedule_detail.html", {
        "schedule": schedule,
        "entries": schedule.entries.all(),
        "is_client": is_client,
        "is_caregiver": is_caregiver,
        "is_support": is_support,
        "is_staff": is_staff,
    })


@login_required
def schedule_edit(request, pk):
    """
    Client edits a DRAFT schedule.
    Blocked after submission.
    """
    from .models import Schedule, ScheduleEntry, ClientProfile
    from .forms import ScheduleForm, ScheduleEntryForm
    from django.forms import formset_factory

    schedule = get_object_or_404(Schedule, pk=pk)

    # Permission check
    try:
        client_profile = request.user.profile.client_profile
    except Exception:
        messages.error(request, "Only clients can edit schedules.")
        return redirect("dashboard_redirect")

    if schedule.client != client_profile:
        messages.error(request, "You can only edit your own schedules.")
        return redirect("dashboard_redirect")

    if not schedule.is_editable_by_client:
        messages.warning(
            request,
            "Submitted schedules cannot be edited. "
            "To make changes, cancel this schedule and create a new one."
        )
        return redirect("schedule_detail", pk=pk)

    organization = get_active_organization(request)
    EntryFormSet = formset_factory(ScheduleEntryForm, extra=1, can_delete=True)

    existing_entries = list(schedule.entries.all())

    if request.method == "POST":
        form = ScheduleForm(request.POST, client_profile=client_profile)
        formset = EntryFormSet(request.POST, prefix="entries")

        if form.is_valid() and formset.is_valid():
            valid_entries = [
                f for f in formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if not valid_entries:
                messages.error(request, "Please keep at least one day/time entry.")
            else:
                matched = form.cleaned_data["match"]
                schedule.caregiver = matched.caregiver
                schedule.support_person = form.cleaned_data.get("support_person")
                schedule.match = matched
                schedule.notes = form.cleaned_data.get("notes", "")
                schedule.start_date = form.cleaned_data["start_date"]
                schedule.frequency = form.cleaned_data["frequency"]
                schedule.custom_interval_weeks = form.cleaned_data.get("custom_interval_weeks")
                schedule.end_date = form.cleaned_data.get("end_date")
                schedule.save()

                # Replace all entries
                schedule.entries.all().delete()
                for entry_form in valid_entries:
                    ScheduleEntry.objects.create(
                        schedule=schedule,
                        day_of_week=entry_form.cleaned_data["day_of_week"],
                        start_time=entry_form.cleaned_data["start_time"],
                        end_time=entry_form.cleaned_data["end_time"],
                    )
                messages.success(request, "Schedule updated.")
                return redirect("schedule_detail", pk=pk)
    else:
        initial_form = {
            "caregiver": schedule.caregiver,
            "support_person": schedule.support_person,
            "match": schedule.match,
            "notes": schedule.notes,
            "start_date": schedule.start_date,
            "frequency": schedule.frequency,
            "custom_interval_weeks": schedule.custom_interval_weeks,
            "end_date": schedule.end_date,
        }
        form = ScheduleForm(initial=initial_form, client_profile=client_profile)
        initial_entries = [
            {
                "day_of_week": e.day_of_week,
                "start_time": e.start_time,
                "end_time": e.end_time,
            }
            for e in existing_entries
        ]
        formset = EntryFormSet(initial=initial_entries, prefix="entries")

    return render(request, "registry/schedule_form.html", {
        "form": form,
        "formset": formset,
        "action": "edit",
        "schedule": schedule,
        "page_title": "Edit Schedule",
    })


@login_required
def schedule_submit(request, pk):
    """
    Client submits a draft schedule to the caregiver/support person.
    POST only. Locked after submission.
    """
    from .models import Schedule
    from django.utils import timezone as tz

    schedule = get_object_or_404(Schedule, pk=pk)

    try:
        client_profile = request.user.profile.client_profile
    except Exception:
        messages.error(request, "Only clients can submit schedules.")
        return redirect("dashboard_redirect")

    if schedule.client != client_profile:
        messages.error(request, "You can only submit your own schedules.")
        return redirect("dashboard_redirect")

    if schedule.status != "draft":
        messages.warning(request, "This schedule has already been submitted.")
        return redirect("schedule_detail", pk=pk)

    if not schedule.entries.exists():
        messages.error(request, "Cannot submit a schedule with no entries.")
        return redirect("schedule_detail", pk=pk)

    if request.method == "POST":
        schedule.status = "submitted"
        schedule.submitted_at = tz.now()
        schedule.save()
        messages.success(request, "Schedule submitted. The careworker and support person will review it.")
        return redirect("schedule_detail", pk=pk)

    return redirect("schedule_detail", pk=pk)


@login_required
def schedule_cancel(request, pk):
    """
    Client soft-cancels a submitted schedule.
    POST only.
    """
    from .models import Schedule
    from django.utils import timezone as tz

    schedule = get_object_or_404(Schedule, pk=pk)

    try:
        client_profile = request.user.profile.client_profile
    except Exception:
        messages.error(request, "Only clients can cancel schedules.")
        return redirect("dashboard_redirect")

    if schedule.client != client_profile:
        messages.error(request, "You can only cancel your own schedules.")
        return redirect("dashboard_redirect")

    if schedule.status == "cancelled":
        messages.info(request, "This schedule is already cancelled.")
        return redirect("schedule_detail", pk=pk)

    if schedule.status == "approved":
        messages.error(request, "An approved schedule cannot be cancelled.")
        return redirect("schedule_detail", pk=pk)

    if request.method == "POST":
        schedule.status = "cancelled"
        schedule.cancelled_at = tz.now()
        schedule.save()
        messages.success(request, "Schedule cancelled. You may create a new schedule.")
        return redirect("client_dashboard")

    return redirect("schedule_detail", pk=pk)


@login_required
def schedule_entry_caregiver_respond(request, entry_pk, action):
    """
    Caregiver approves or rejects a single schedule entry.
    action: 'approve' | 'reject'
    POST only.
    """
    from .models import ScheduleEntry
    from .forms import ScheduleEntryReviewForm
    from django.utils import timezone as tz

    entry = get_object_or_404(
        ScheduleEntry.objects.select_related("schedule__caregiver__user_profile"),
        pk=entry_pk,
    )

    try:
        caregiver_profile = request.user.profile.caregiver_profile
    except Exception:
        messages.error(request, "Only careworkers can respond to schedule entries.")
        return redirect("dashboard_redirect")

    if entry.schedule.caregiver != caregiver_profile:
        messages.error(request, "You can only respond to schedules assigned to you.")
        return redirect("dashboard_redirect")

    if entry.schedule.status in ("draft", "cancelled"):
        messages.error(request, "Cannot respond to a draft or cancelled schedule.")
        return redirect("schedule_detail", pk=entry.schedule.pk)

    if request.method == "POST":
        form = ScheduleEntryReviewForm(request.POST)
        if form.is_valid():
            if action == "approve":
                entry.caregiver_status = "approved"
            elif action == "reject":
                entry.caregiver_status = "rejected"
                entry.caregiver_notes = form.cleaned_data.get("notes", "")
            else:
                messages.error(request, "Invalid action.")
                return redirect("schedule_detail", pk=entry.schedule.pk)

            entry.caregiver_reviewed_at = tz.now()
            entry.save()
            entry.schedule.update_status_from_entries()
            messages.success(request, f"Entry {action}d.")
        return redirect("schedule_detail", pk=entry.schedule.pk)

    return redirect("schedule_detail", pk=entry.schedule.pk)


@login_required
def schedule_entry_support_respond(request, entry_pk, action):
    """
    Support person/coordinator approves or rejects a single schedule entry.
    action: 'approve' | 'reject'
    POST only.
    """
    from .models import ScheduleEntry
    from .forms import ScheduleEntryReviewForm
    from django.utils import timezone as tz

    entry = get_object_or_404(
        ScheduleEntry.objects.select_related("schedule__support_person__user_profile"),
        pk=entry_pk,
    )

    try:
        coordinator_profile = request.user.profile.support_coordinator_profile
    except Exception:
        messages.error(request, "Only support persons can respond to schedule entries.")
        return redirect("dashboard_redirect")

    if entry.schedule.support_person != coordinator_profile:
        messages.error(request, "You can only respond to schedules assigned to you.")
        return redirect("dashboard_redirect")

    if entry.schedule.status in ("draft", "cancelled"):
        messages.error(request, "Cannot respond to a draft or cancelled schedule.")
        return redirect("schedule_detail", pk=entry.schedule.pk)

    if request.method == "POST":
        form = ScheduleEntryReviewForm(request.POST)
        if form.is_valid():
            if action == "approve":
                entry.support_person_status = "approved"
            elif action == "reject":
                entry.support_person_status = "rejected"
                entry.support_person_notes = form.cleaned_data.get("notes", "")
            else:
                messages.error(request, "Invalid action.")
                return redirect("schedule_detail", pk=entry.schedule.pk)

            entry.support_person_reviewed_at = tz.now()
            entry.save()
            entry.schedule.update_status_from_entries()
            messages.success(request, f"Entry {action}d.")
        return redirect("schedule_detail", pk=entry.schedule.pk)

    return redirect("schedule_detail", pk=entry.schedule.pk)


@login_required
def schedule_delete(request, pk):
    """
    Client permanently deletes a schedule (and its entries via cascade).
    POST only. No status restriction — any schedule owned by this client
    may be deleted.
    """
    from .models import Schedule

    schedule = get_object_or_404(Schedule, pk=pk)

    try:
        client_profile = request.user.profile.client_profile
    except Exception:
        messages.error(request, "Only clients can delete schedules.")
        return redirect("dashboard_redirect")

    if schedule.client != client_profile:
        messages.error(request, "You can only delete your own schedules.")
        return redirect("dashboard_redirect")

    if request.method == "POST":
        schedule.delete()
        messages.success(request, "Schedule deleted.")
        return redirect("client_dashboard")

    return redirect("schedule_detail", pk=pk)


# ── Internal helper used by schedule views ───────────────────────────────────

def _is_admin_or_staff(request):
    """Return True if the current user has admin or staff role in any org."""
    from organizations.models import OrganizationStaff
    return OrganizationStaff.objects.filter(
        staff_profile__user_profile=request.user.profile,
        status="active",
    ).exists()


# =============================================================================
# Schedule Entry Rating Views
# =============================================================================

@login_required
def schedule_entry_rate(request, entry_pk):
    """
    Show + process the Rate Experience form for a single approved ScheduleEntry.
    Only the schedule's client or caregiver may access this view.
    The entry must be fully approved before rating is allowed.
    """
    from .models import ScheduleEntry, ScheduleEntryRating
    from .forms import ScheduleEntryRatingForm
    from django.db.models import Avg

    entry = get_object_or_404(
        ScheduleEntry.objects.select_related(
            "schedule__client__user_profile",
            "schedule__caregiver__user_profile",
            "schedule__support_person",
        ),
        pk=entry_pk,
    )
    schedule = entry.schedule

    # ── Determine who is calling ──────────────────────────────────────────────
    rater_role = None
    user_profile = request.user.profile

    try:
        if schedule.client.user_profile == user_profile:
            rater_role = "client"
    except Exception:
        pass

    if rater_role is None:
        try:
            if schedule.caregiver.user_profile == user_profile:
                rater_role = "caregiver"
        except Exception:
            pass

    if rater_role is None:
        messages.error(request, "You do not have permission to rate this entry.")
        return redirect("schedule_detail", pk=schedule.pk)

    # ── Gate: only fully approved entries can be rated ────────────────────────
    if not entry.is_fully_approved:
        messages.warning(
            request,
            "This schedule entry must be fully approved before it can be rated."
        )
        return redirect("schedule_detail", pk=schedule.pk)

    # ── Existing rating by this user for this entry (if any) for pre-fill ────
    existing_ratings = ScheduleEntryRating.objects.filter(
        schedule_entry=entry,
        rater_profile=user_profile,
    ).order_by("-rating_date")

    # ── Handle form ───────────────────────────────────────────────────────────
    if request.method == "POST":
        form = ScheduleEntryRatingForm(request.POST, entry=entry)
        if form.is_valid():
            cd = form.cleaned_data
            rating, created = ScheduleEntryRating.objects.update_or_create(
                schedule_entry=entry,
                rater_profile=user_profile,
                rating_date=cd["rating_date"],
                defaults={
                    "rater_role": rater_role,
                    "care_fit_respect": cd["care_fit_respect"],
                    "communication_coordination": cd["communication_coordination"],
                    "reliability_consistency": cd["reliability_consistency"],
                    "workload_support_balance": cd["workload_support_balance"],
                    "notes": cd.get("notes", ""),
                },
            )
            verb = "updated" if not created else "submitted"
            messages.success(request, f"Rating {verb} for {entry.get_day_of_week_display()}.")
            return redirect("schedule_detail", pk=schedule.pk)
    else:
        form = ScheduleEntryRatingForm(entry=entry)

    # ── Context ───────────────────────────────────────────────────────────────
    # Counterpart name (show who you're rating with)
    if rater_role == "client":
        counterpart_name = schedule.caregiver.user_profile.display_name
    else:
        counterpart_name = schedule.client.user_profile.display_name

    return render(request, "registry/schedule_entry_rate.html", {
        "form": form,
        "entry": entry,
        "schedule": schedule,
        "rater_role": rater_role,
        "counterpart_name": counterpart_name,
        "existing_ratings": existing_ratings,
    })


# ── Rating helpers ────────────────────────────────────────────────────────────

def _get_rating_summary(profile, role):
    """
    Return average rating data received by a caregiver (rated by clients)
    or by a client (rated by caregivers).
    `profile` is a CaregiverProfile or ClientProfile.
    `role` is "caregiver" or "client".
    """
    from .models import ScheduleEntryRating
    from django.db.models import Avg, F as _F

    # Ratings are submitted *about* a person by the counterpart.
    # A caregiver's ratings are those submitted by clients about caregiver sessions.
    # A client's ratings are those submitted by caregivers about client sessions.
    counterpart_role = "client" if role == "caregiver" else "caregiver"

    if role == "caregiver":
        qs = ScheduleEntryRating.objects.filter(
            schedule_entry__schedule__caregiver=profile,
            rater_role=counterpart_role,
        )
    else:
        qs = ScheduleEntryRating.objects.filter(
            schedule_entry__schedule__client=profile,
            rater_role=counterpart_role,
        )

    agg = qs.aggregate(
        avg_overall=Avg(
            (_F("care_fit_respect")
             + _F("communication_coordination")
             + _F("reliability_consistency")
             + _F("workload_support_balance")) / 4.0
        ),
        avg_care_fit=Avg("care_fit_respect"),
        avg_communication=Avg("communication_coordination"),
        avg_reliability=Avg("reliability_consistency"),
        avg_workload=Avg("workload_support_balance"),
    )
    return {
        "count": qs.count(),
        **agg,
    }


@login_required
def caregiver_ratings_detail(request, pk):
    """
    Staff-only: Full ratings history received by a specific careworker.
    pk is CaregiverProfile.pk.
    """
    from .models import CaregiverProfile, ScheduleEntryRating

    unauthorized = _redirect_if_not_admin_staff(request)
    if unauthorized:
        return unauthorized

    caregiver_profile = get_object_or_404(CaregiverProfile.objects.select_related("user_profile"), pk=pk)

    ratings_qs = ScheduleEntryRating.objects.filter(
        schedule_entry__schedule__caregiver=caregiver_profile,
        rater_role="client",
    ).select_related(
        "schedule_entry__schedule__client__user_profile",
        "rater_profile",
    ).order_by("-rating_date")

    paginator = Paginator(ratings_qs, 20)
    page = paginator.get_page(request.GET.get("page", 1))

    summary = _get_rating_summary(caregiver_profile, "caregiver")

    return render(request, "registry/caregiver_ratings_detail.html", {
        "caregiver_profile": caregiver_profile,
        "ratings": page,
        "summary": summary,
    })


@login_required
def client_ratings_detail(request, pk):
    """
    Staff-only: Full ratings history received by a specific client.
    pk is ClientProfile.pk.
    """
    from .models import ClientProfile, ScheduleEntryRating

    unauthorized = _redirect_if_not_admin_staff(request)
    if unauthorized:
        return unauthorized

    client_profile = get_object_or_404(ClientProfile.objects.select_related("user_profile"), pk=pk)

    ratings_qs = ScheduleEntryRating.objects.filter(
        schedule_entry__schedule__client=client_profile,
        rater_role="caregiver",
    ).select_related(
        "schedule_entry__schedule__caregiver__user_profile",
        "rater_profile",
    ).order_by("-rating_date")

    paginator = Paginator(ratings_qs, 20)
    page = paginator.get_page(request.GET.get("page", 1))

    summary = _get_rating_summary(client_profile, "client")

    return render(request, "registry/client_ratings_detail.html", {
        "client_profile": client_profile,
        "ratings": page,
        "summary": summary,
    })


# ==============================================
# Self-Service Profile View & Edit Views
# ==============================================

def _resolve_choices(keys, choices_list):
    """Convert a list of stored choice keys → their human-readable labels."""
    mapping = dict(choices_list)
    return [mapping.get(k, k) for k in (keys or [])]


def _availability_initial(availability_dict):
    """Build the `initial` dict for availability form fields from a stored JSON dict."""
    from .forms import DAYS
    return {f"{day}_periods": availability_dict.get(day, []) for day in DAYS}


# ── Careworker ────────────────────────────────────────────────────────────────

@login_required
def caregiver_profile_view(request):
    """Show the logged-in careworker's own profile with Edit buttons per section."""
    from .models import CaregiverProfile
    from .models import (
        TRANSPORTATION_CHOICES, EXPERIENCE_CHOICES, LANGUAGE_CHOICES,
        PATHOGEN_PROTOCOL_CHOICES, ATTENDANT_PROGRAM_CHOICES,
        HOURS_LOOKING_FOR_CHOICES, RATE_CHOICES,
    )

    profile = get_object_or_404(CaregiverProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)
    up = profile.user_profile

    return render(request, "registry/profile/caregiver_profile.html", {
        "profile": profile,
        "user_profile": up,
        "transportation_display": _resolve_choices(profile.transportation, TRANSPORTATION_CHOICES),
        "experience_display": _resolve_choices(profile.experience_with, EXPERIENCE_CHOICES),
        "languages_display": _resolve_choices(profile.languages_spoken, LANGUAGE_CHOICES),
        "protocols_display": _resolve_choices(profile.pathogen_protocols, PATHOGEN_PROTOCOL_CHOICES),
        "programs_display": _resolve_choices(profile.attendant_care_programs, ATTENDANT_PROGRAM_CHOICES),
        "hours_display": dict(HOURS_LOOKING_FOR_CHOICES).get(profile.hours_looking_for, profile.hours_looking_for),
        "rate_display": dict(RATE_CHOICES).get(profile.rate, profile.rate),
        "contact_prefs_display": _resolve_choices(up.contact_preferences, [("phone","Phone"),("email","Email"),("text","Text Message"),("any","Any")]),
        "pronouns_display": dict([("she_her","She/Her"),("he_him","He/Him"),("they_them","They/Them"),("she_they","She/They"),("he_they","He/They"),("ze_zir","Ze/Zir"),("ask_me","Ask Me"),("self_describe","Self Describe")]).get(up.pronouns, up.pronouns),
    })


@login_required
def caregiver_profile_edit_identity(request):
    from .models import CaregiverProfile
    from .forms import IdentityEditForm

    profile = get_object_or_404(CaregiverProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)
    up = profile.user_profile

    if request.method == "POST":
        form = IdentityEditForm(request.POST)
        if form.is_valid():
            form.save(up)
            messages.success(request, "Identity & contact info updated.")
            return redirect("caregiver_profile")
    else:
        form = IdentityEditForm(initial={
            "first_name": up.user.first_name,
            "last_name": up.user.last_name,
            "phone": up.phone,
            "pronouns": up.pronouns,
            "contact_preferences": up.contact_preferences,
            "address": up.address,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Identity & Contact",
        "back_url_name": "caregiver_profile",
    })


@login_required
def caregiver_profile_edit_location(request):
    from .models import CaregiverProfile
    from .forms import CaregiverLocationEditForm

    profile = get_object_or_404(CaregiverProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)

    if request.method == "POST":
        form = CaregiverLocationEditForm(request.POST)
        if form.is_valid():
            form.save(profile)
            messages.success(request, "Location & transportation updated.")
            return redirect("caregiver_profile")
    else:
        form = CaregiverLocationEditForm(initial={
            "base_zip_code": profile.base_zip_code,
            "willing_to_work_cities": ", ".join(profile.willing_to_work_cities or []),
            "transportation": profile.transportation,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Location & Transportation",
        "back_url_name": "caregiver_profile",
    })


@login_required
def caregiver_profile_edit_availability(request):
    from .models import CaregiverProfile
    from .forms import CaregiverAvailabilityEditForm

    profile = get_object_or_404(CaregiverProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)

    if request.method == "POST":
        form = CaregiverAvailabilityEditForm(request.POST)
        if form.is_valid():
            form.save(profile)
            messages.success(request, "Availability & rates updated.")
            return redirect("caregiver_profile")
    else:
        initial = _availability_initial(profile.availability)
        initial.update({
            "hours_looking_for": profile.hours_looking_for,
            "desired_hours_per_week": profile.desired_hours_per_week,
            "rate": profile.rate,
            "attendant_care_programs": profile.attendant_care_programs,
        })
        form = CaregiverAvailabilityEditForm(initial=initial)

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Availability & Hours",
        "back_url_name": "caregiver_profile",
    })


@login_required
def caregiver_profile_edit_experience(request):
    from .models import CaregiverProfile
    from .forms import CaregiverExperienceEditForm

    profile = get_object_or_404(CaregiverProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)

    if request.method == "POST":
        form = CaregiverExperienceEditForm(request.POST)
        if form.is_valid():
            form.save(profile)
            messages.success(request, "Experience & skills updated.")
            return redirect("caregiver_profile")
    else:
        form = CaregiverExperienceEditForm(initial={
            "experience_with": profile.experience_with,
            "languages_spoken": profile.languages_spoken,
            "pathogen_protocols": profile.pathogen_protocols,
            "certified_ihss_worker": profile.certified_ihss_worker,
            "additional_certifications": profile.additional_certifications,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Experience & Skills",
        "back_url_name": "caregiver_profile",
    })


@login_required
def caregiver_profile_edit_notes(request):
    from .models import CaregiverProfile
    from .forms import CaregiverNotesEditForm

    profile = get_object_or_404(CaregiverProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)

    if request.method == "POST":
        form = CaregiverNotesEditForm(request.POST)
        if form.is_valid():
            form.save(profile)
            messages.success(request, "Profile notes updated.")
            return redirect("caregiver_profile")
    else:
        form = CaregiverNotesEditForm(initial={
            "bio": profile.bio,
            "wants_training_updates": profile.wants_training_updates,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Profile Notes",
        "back_url_name": "caregiver_profile",
    })


# ── Client ────────────────────────────────────────────────────────────────────

@login_required
def client_profile_view(request):
    """Show the logged-in client's own profile with Edit buttons per section."""
    from .models import ClientProfile
    from .models import (
        ATTENDANT_PROGRAM_CHOICES, LANGUAGE_CHOICES,
        CARE_NEEDS_CHOICES, PATHOGEN_PROTOCOL_CHOICES,
    )

    profile = get_object_or_404(ClientProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)
    up = profile.user_profile

    return render(request, "registry/profile/client_profile.html", {
        "profile": profile,
        "user_profile": up,
        "programs_display": _resolve_choices(profile.attendant_care_programs, ATTENDANT_PROGRAM_CHOICES),
        "languages_display": _resolve_choices(profile.languages_preferred, LANGUAGE_CHOICES),
        "care_needs_display": _resolve_choices(profile.care_needs, CARE_NEEDS_CHOICES),
        "protocols_display": _resolve_choices(profile.pathogen_protocol_preferences, PATHOGEN_PROTOCOL_CHOICES),
        "contact_prefs_display": _resolve_choices(up.contact_preferences, [("phone","Phone"),("email","Email"),("text","Text Message"),("any","Any")]),
        "pronouns_display": dict([("she_her","She/Her"),("he_him","He/Him"),("they_them","They/Them"),("she_they","She/They"),("he_they","He/They"),("ze_zir","Ze/Zir"),("ask_me","Ask Me"),("self_describe","Self Describe")]).get(up.pronouns, up.pronouns),
    })


@login_required
def client_profile_edit_identity(request):
    from .models import ClientProfile
    from .forms import IdentityEditForm

    profile = get_object_or_404(ClientProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)
    up = profile.user_profile

    if request.method == "POST":
        form = IdentityEditForm(request.POST)
        if form.is_valid():
            form.save(up)
            messages.success(request, "Identity & contact info updated.")
            return redirect("client_profile")
    else:
        form = IdentityEditForm(initial={
            "first_name": up.user.first_name,
            "last_name": up.user.last_name,
            "phone": up.phone,
            "pronouns": up.pronouns,
            "contact_preferences": up.contact_preferences,
            "address": up.address,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Identity & Contact",
        "back_url_name": "client_profile",
    })


@login_required
def client_profile_edit_programs(request):
    from .models import ClientProfile
    from .forms import ClientProgramsEditForm

    profile = get_object_or_404(ClientProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)

    if request.method == "POST":
        form = ClientProgramsEditForm(request.POST)
        if form.is_valid():
            form.save(profile)
            messages.success(request, "Programs & language preferences updated.")
            return redirect("client_profile")
    else:
        form = ClientProgramsEditForm(initial={
            "base_zip_code": profile.base_zip_code,
            "attendant_care_programs": profile.attendant_care_programs,
            "languages_preferred": profile.languages_preferred,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Programs & Language",
        "back_url_name": "client_profile",
    })


@login_required
def client_profile_edit_availability(request):
    from .models import ClientProfile
    from .forms import ClientAvailabilityEditForm

    profile = get_object_or_404(ClientProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)

    if request.method == "POST":
        form = ClientAvailabilityEditForm(request.POST)
        if form.is_valid():
            form.save(profile)
            messages.success(request, "Availability updated.")
            return redirect("client_profile")
    else:
        initial = _availability_initial(profile.availability)
        initial.update({
            "schedule_flexibility": profile.schedule_flexibility,
            "hours_per_week": profile.hours_per_week,
        })
        form = ClientAvailabilityEditForm(initial=initial)

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Availability",
        "back_url_name": "client_profile",
    })


@login_required
def client_profile_edit_care_needs(request):
    from .models import ClientProfile
    from .forms import ClientCareNeedsEditForm

    profile = get_object_or_404(ClientProfile.objects.select_related("user_profile__user"), user_profile__user=request.user)

    if request.method == "POST":
        form = ClientCareNeedsEditForm(request.POST)
        if form.is_valid():
            form.save(profile)
            messages.success(request, "Care needs updated.")
            return redirect("client_profile")
    else:
        form = ClientCareNeedsEditForm(initial={
            "care_needs": profile.care_needs,
            "additional_care_needs": profile.additional_care_needs,
            "pathogen_protocol_preferences": profile.pathogen_protocol_preferences,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Care Needs & Protocols",
        "back_url_name": "client_profile",
    })


# ── Support Coordinator ───────────────────────────────────────────────────────

@login_required
def coordinator_profile_view(request):
    """Show the logged-in support coordinator's own profile with Edit buttons per section."""
    from .models import SupportCoordinatorProfile

    profile = get_object_or_404(
        SupportCoordinatorProfile.objects.select_related("user_profile__user"),
        user_profile__user=request.user,
    )
    up = profile.user_profile

    return render(request, "registry/profile/coordinator_profile.html", {
        "profile": profile,
        "user_profile": up,
        "contact_prefs_display": _resolve_choices(up.contact_preferences, [("phone","Phone"),("email","Email"),("text","Text Message"),("any","Any")]),
        "pronouns_display": dict([("she_her","She/Her"),("he_him","He/Him"),("they_them","They/Them"),("she_they","She/They"),("he_they","He/They"),("ze_zir","Ze/Zir"),("ask_me","Ask Me"),("self_describe","Self Describe")]).get(up.pronouns, up.pronouns),
    })


@login_required
def coordinator_profile_edit_identity(request):
    from .models import SupportCoordinatorProfile
    from .forms import IdentityEditForm

    profile = get_object_or_404(
        SupportCoordinatorProfile.objects.select_related("user_profile__user"),
        user_profile__user=request.user,
    )
    up = profile.user_profile

    if request.method == "POST":
        form = IdentityEditForm(request.POST)
        if form.is_valid():
            form.save(up)
            messages.success(request, "Identity & contact info updated.")
            return redirect("coordinator_profile")
    else:
        form = IdentityEditForm(initial={
            "first_name": up.user.first_name,
            "last_name": up.user.last_name,
            "phone": up.phone,
            "pronouns": up.pronouns,
            "contact_preferences": up.contact_preferences,
            "address": up.address,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Identity & Contact",
        "back_url_name": "coordinator_profile",
    })


@login_required
def coordinator_profile_edit_info(request):
    from .models import SupportCoordinatorProfile
    from .forms import CoordinatorInfoEditForm

    profile = get_object_or_404(
        SupportCoordinatorProfile.objects.select_related("user_profile__user"),
        user_profile__user=request.user,
    )

    if request.method == "POST":
        form = CoordinatorInfoEditForm(request.POST)
        if form.is_valid():
            form.save(profile)
            messages.success(request, "Coordinator info updated.")
            return redirect("coordinator_profile")
    else:
        form = CoordinatorInfoEditForm(initial={
            "relationship_to_clients": profile.relationship_to_clients,
            "credentials": profile.credentials,
            "certifications": profile.certifications,
        })

    return render(request, "registry/profile/profile_edit_form.html", {
        "form": form,
        "section_title": "Edit Coordinator Info",
        "back_url_name": "coordinator_profile",
    })
