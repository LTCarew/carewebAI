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
    Route users to appropriate dashboard based on their role in the active organization.
    """
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
        return redirect("admin_dashboard")
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
def admin_dashboard(request):
    """Admin dashboard showing pending and approved applications."""
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    # Get active organization for filtering
    active_org = get_active_organization(request)
    
    # Scope queries by organization if available
    if active_org:
        org_caregivers = OrganizationCaregiver.objects.filter(
            organization=active_org
        ).select_related('caregiver_profile__user_profile').order_by("status", "-created_at")
        
        org_clients = OrganizationClient.objects.filter(
            organization=active_org
        ).select_related('client_profile__user_profile').order_by("status", "-created_at")
        
        organization_name = active_org.name
    else:
        # Fallback to all if no org (shouldn't happen for admins)
        org_caregivers = OrganizationCaregiver.objects.all().select_related(
            'caregiver_profile__user_profile'
        ).order_by("status", "-created_at")
        
        org_clients = OrganizationClient.objects.all().select_related(
            'client_profile__user_profile'
        ).order_by("status", "-created_at")
        
        organization_name = ""

    full_name = request.user.get_full_name().strip() or request.user.username

    return render(request, "registry/admin_dashboard.html", {
        "org_caregivers": org_caregivers,
        "org_clients": org_clients,
        "pending_caregivers": org_caregivers.filter(status="pending").count(),
        "pending_clients": org_clients.filter(status="pending").count(),
        "approved_caregivers": org_caregivers.filter(status="approved").count(),
        "approved_clients": org_clients.filter(status="approved").count(),
        "admin_display_name": full_name,
        "admin_organization_name": organization_name,
    })


@login_required
def caregiver_detail(request, pk):
    """Display caregiver application/profile details."""
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    org_caregiver = get_object_or_404(
        OrganizationCaregiver.objects.select_related(
            'caregiver_profile__user_profile',
            'organization'
        ),
        pk=pk
    )

    return render(request, "registry/caregiver_detail.html", {
        "org_caregiver": org_caregiver
    })


@login_required
def client_detail(request, pk):
    """Display client application/profile details."""
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    org_client = get_object_or_404(
        OrganizationClient.objects.select_related(
            'client_profile__user_profile',
            'organization'
        ),
        pk=pk
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
