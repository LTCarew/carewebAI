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
    
    return render(request, "registry/coordinator_dashboard.html", {
        "coordinator_profile": coordinator_profile,
        "client_relationships": client_relationships,
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
            # Save creates the profile and marks invite as used
            client_coordinator = form.save(invite)
            
            messages.success(
                request,
                f"Welcome! You are now a support coordinator for {invite.client_profile.user_profile.display_name}."
            )
            
            # Log the user in (they now have an account)
            from django.contrib.auth import login
            from .services import get_or_create_user_from_email
            
            user = get_or_create_user_from_email(form.cleaned_data['email'])
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
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
        messages.error(request, "Could not load your caregiver profile.")
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

    return render(request, "registry/caregiver_dashboard.html", {
        "caregiver_profile": caregiver_profile,
        "pending_my_approval": pending_my_approval,
        "pending_client": pending_client,
        "active_matches": active_matches,
        "declined_matches": declined_matches,
        "unread_notifications": unread_notifications,
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
        messages.error(request, "Could not load your client profile.")
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

    return render(request, "registry/client_dashboard.html", {
        "client_profile": client_profile,
        "pending_my_approval": pending_my_approval,
        "pending_caregiver": pending_caregiver,
        "active_matches": active_matches,
        "declined_matches": declined_matches,
        "unread_notifications": unread_notifications,
        "coordinators": coordinators,
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
    match_results = None       # Only populated after the user submits criteria
    match_direction = None     # "find_clients" or "find_caregivers"

    # ── Caregiver: they are the caregiver; select tags to find matching clients ──
    if user_role == "caregiver":
        try:
            caregiver_profile = request.user.profile.caregiver_profile
        except Exception:
            messages.error(request, "Could not load your caregiver profile.")
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

        if tag_ids:
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
                for r in _find(caregiver_profile, org_obj, limit=200, tag_ids=tag_ids):
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
            messages.error(request, "Could not load your client profile.")
            return redirect("dashboard_redirect")

        client_org_ids = OrganizationClient.objects.filter(
            client_profile=client_profile,
            status="approved",
        ).values_list("organization_id", flat=True)

        match_direction = "find_caregivers"

        if tag_ids:
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

            if selected_caregiver and tag_ids:
                raw_results = find_best_clients_for_caregiver(
                    selected_caregiver, organization, limit=200, tag_ids=tag_ids
                )
                match_results = Paginator(raw_results, 10).get_page(request.GET.get("page", 1))

        else:  # find_caregivers
            client_id = request.GET.get("client_id")
            if client_id:
                try:
                    selected_client = ClientProfile.objects.get(pk=client_id)
                except ClientProfile.DoesNotExist:
                    pass

            if selected_client and tag_ids:
                raw_results = find_best_caregivers_for_client(
                    selected_client, organization, limit=200, tag_ids=tag_ids
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
    role_display = user_role.title() if user_role else "Staff"
    
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
    if selected_view not in ("caregivers", "clients"):
        selected_view = "caregivers"

    # Paginate the caregiver and client application lists
    caregivers_page = Paginator(caregiver_data, 10).get_page(request.GET.get("caregivers_page", 1))
    clients_page = Paginator(client_data, 10).get_page(request.GET.get("clients_page", 1))

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

    is_admin_staff = _redirect_if_not_admin_staff(request) is None

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
        messages.error(request, "You don't have access to that caregiver's profile.")
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

    is_admin_staff = _redirect_if_not_admin_staff(request) is None

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
        messages.error(request, "You don't have access to that client's profile.")
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
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect
    
    # Get active organization
    active_org = get_active_organization(request)
    
    if not active_org:
        messages.error(request, "No active organization found.")
        return redirect("org_dashboard")
    
    # Get all caregiver profiles
    all_caregivers = CaregiverProfile.objects.select_related('user_profile').all()
    
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
