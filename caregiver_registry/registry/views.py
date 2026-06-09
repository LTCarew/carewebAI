"""Registry views for application intake, dashboards, and admin review workflow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
                f"Welcome! You are now a support coordinator for {invite.client_profile.user_profile.name}."
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
            f"Permissions updated for {relationship.coordinator_profile.user_profile.name}."
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
    return render(request, "registry/caregiver_dashboard.html")


@login_required
def client_dashboard(request):
    return render(request, "registry/client_dashboard.html")


@login_required
def registry_network(request):
    """Unified registry page with role-based visibility."""
    # Get active organization
    organization = get_active_organization(request)
    
    if not organization:
        messages.warning(request, "Your account is not linked to an organization yet.")
        return redirect("dashboard_redirect")

    # Get user's role in the organization
    user_role = get_user_primary_role(request.user, organization)
    
    if not user_role:
        messages.warning(request, "You do not have an active role in this organization.")
        return redirect("dashboard_redirect")

    # Query approved caregivers and clients for this organization
    org_caregivers = OrganizationCaregiver.objects.filter(
        organization=organization,
        status='approved'
    ).select_related('caregiver_profile__user_profile').order_by('-created_at')
    
    org_clients = OrganizationClient.objects.filter(
        organization=organization,
        status='approved'
    ).select_related('client_profile__user_profile').order_by('-created_at')

    selected_view = ""
    if user_role == "client":
        selected_view = "caregivers"
    elif user_role == "caregiver":
        selected_view = "clients"
    elif user_role in ["admin", "staff"]:
        requested_view = request.GET.get("view", "clients")
        selected_view = requested_view if requested_view in ["clients", "caregivers"] else "clients"
    else:
        messages.error(request, "Unsupported account role for registry access.")
        return redirect("dashboard_redirect")

    return render(request, "registry/network_registry.html", {
        "selected_view": selected_view,
        "is_admin_staff": user_role in ["admin", "staff"],
        "organization_name": organization.name,
        "org_caregivers": org_caregivers,
        "org_clients": org_clients,
    })


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
            'name': caregiver.user_profile.name,
            'email': caregiver.user_profile.email,
            'status': rel.status if rel else 'pending',
            'relationship': rel
        })
    
    client_data = []
    for client in all_clients:
        rel = client_relationships.get(client.id)
        client_data.append({
            'pk': rel.pk if rel else None,
            'profile_id': client.id,
            'name': client.user_profile.name,
            'email': client.user_profile.email,
            'status': rel.status if rel else 'pending',
            'relationship': rel
        })
    
    # Count by status
    pending_caregivers = sum(1 for c in caregiver_data if c['status'] == 'pending')
    approved_caregivers = sum(1 for c in caregiver_data if c['status'] == 'approved')
    pending_clients = sum(1 for c in client_data if c['status'] == 'pending')
    approved_clients = sum(1 for c in client_data if c['status'] == 'approved')
    
    full_name = request.user.get_full_name().strip() or request.user.username

    return render(request, "registry/org_dashboard.html", {
        "caregivers": caregiver_data,
        "clients": client_data,
        "pending_caregivers": pending_caregivers,
        "pending_clients": pending_clients,
        "approved_caregivers": approved_caregivers,
        "approved_clients": approved_clients,
        "user_display_name": full_name,
        "organization_name": organization_name,
        "user_role": role_display,
    })


@login_required
def caregiver_detail(request, pk):
    """
    Display caregiver application/profile details.
    If pk is for a profile (not a relationship), create the relationship first.
    """
    from .models import CaregiverProfile
    
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    active_org = get_active_organization(request)
    
    # Try to get as OrganizationCaregiver first
    try:
        org_caregiver = OrganizationCaregiver.objects.select_related(
            'caregiver_profile__user_profile',
            'organization'
        ).get(pk=pk)
    except OrganizationCaregiver.DoesNotExist:
        # Maybe pk is actually a profile_id, create the relationship
        caregiver_profile = get_object_or_404(CaregiverProfile, pk=pk)
        org_caregiver, created = OrganizationCaregiver.objects.get_or_create(
            organization=active_org,
            caregiver_profile=caregiver_profile,
            defaults={'status': 'pending'}
        )

    return render(request, "registry/caregiver_detail.html", {
        "org_caregiver": org_caregiver
    })


@login_required
def client_detail(request, pk):
    """
    Display client application/profile details.
    If pk is for a profile (not a relationship), create the relationship first.
    """
    from .models import ClientProfile
    
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    active_org = get_active_organization(request)
    
    # Try to get as OrganizationClient first
    try:
        org_client = OrganizationClient.objects.select_related(
            'client_profile__user_profile',
            'organization'
        ).get(pk=pk)
    except OrganizationClient.DoesNotExist:
        # Maybe pk is actually a profile_id, create the relationship
        client_profile = get_object_or_404(ClientProfile, pk=pk)
        org_client, created = OrganizationClient.objects.get_or_create(
            organization=active_org,
            client_profile=client_profile,
            defaults={'status': 'pending'}
        )

    return render(request, "registry/client_detail.html", {
        "org_client": org_client
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
            caregiver_name = org_caregiver.caregiver_profile.user_profile.name
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
        caregiver_name = org_caregiver.caregiver_profile.user_profile.name
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
            client_name = org_client.client_profile.user_profile.name
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
        client_name = org_client.client_profile.user_profile.name
        messages.success(request, f"{client_name} was marked as {status}.")

    return redirect("client_detail", pk=pk)


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
    
    return render(request, "registry/caregiver_pool.html", {
        "caregivers": available_caregivers,
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
    
    return render(request, "registry/client_pool.html", {
        "clients": available_clients,
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
            f"{caregiver_profile.user_profile.name} added to your organization for review."
        )
    else:
        messages.info(request, f"{caregiver_profile.user_profile.name} is already in your organization.")
    
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
            f"{client_profile.user_profile.name} added to your organization for review."
        )
    else:
        messages.info(request, f"{client_profile.user_profile.name} is already in your organization.")
    
    return redirect("org_dashboard")
