"""Registry views for application intake, dashboards, and admin review workflow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CaregiverApplicationForm, ClientApplicationForm
from .models import Caregiver, Client
from .services import (
    approve_caregiver_application,
    approve_client_application,
    get_active_organization,
    get_user_role_in_organization,
    get_user_memberships,
    set_active_organization,
)


# Keep statuses centralized so update views cannot drift apart.
ALLOWED_STATUSES = ["pending", "approved", "rejected"]


def _user_is_admin_staff(user):
    """
    Return True when the authenticated user has the admin or staff role.
    Uses OrganizationMembership to determine role.
    """
    if not user.is_authenticated:
        return False
    
    # Check if user has admin or staff role in any organization
    from organizations.models import OrganizationMembership
    return OrganizationMembership.objects.filter(
        user=user,
        role__in=['admin', 'staff'],
        status='active'
    ).exists()


def _redirect_if_not_admin_staff(request):
    """Protect admin workflow pages from non-admin users.

    Returns a redirect response for unauthorized users, otherwise None.
    """
    if _user_is_admin_staff(request.user):
        return None

    messages.error(request, "You do not have permission to access the admin registry workflow.")
    return redirect("dashboard_redirect")


def caregiver_apply(request):

    if request.method == "POST":

        form = CaregiverApplicationForm(request.POST)

        if form.is_valid():

            caregiver = form.save(commit=False)
            caregiver.status = "pending"
            caregiver.save()

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

    # Handles client application form submission and rendering
    if request.method == "POST":

        form = ClientApplicationForm(request.POST)

        if form.is_valid():

            client = form.save(commit=False)
            client.status = "pending"
            client.save()

            messages.success(
                request,
                "Application submitted successfully."
            )

            return redirect("application_success")
        
    # Handles GET request by rendering an empty client application form
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
    Route users to appropriate dashboard based on their OrganizationMembership role.
    Uses active organization from session or defaults to first membership.
    """
    # Get active organization
    active_org = get_active_organization(request)
    
    if not active_org:
        messages.warning(request, "Your account is not associated with any organization. Please contact support.")
        return redirect("home")
    
    # Get user's role in the active organization
    role = get_user_role_in_organization(request.user, active_org)
    
    if not role:
        messages.warning(request, "You do not have an active role in this organization. Please contact support.")
        return redirect("home")
    
    # Route based on role
    if role == "admin" or role == "staff":
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
    user_role = get_user_role_in_organization(request.user, organization)
    
    if not user_role:
        messages.warning(request, "You do not have an active role in this organization.")
        return redirect("dashboard_redirect")

    caregivers = Caregiver.objects.filter(organization=organization).order_by("status", "-created_at")
    clients = Client.objects.filter(organization=organization).order_by("status", "-created_at")

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
        "caregivers": caregivers,
        "clients": clients,
    })


@login_required
def admin_dashboard(request):
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    # Get active organization for filtering
    active_org = get_active_organization(request)
    
    # Scope queries by organization if available
    if active_org:
        caregivers = Caregiver.objects.filter(organization=active_org).order_by("status", "-created_at")
        clients = Client.objects.filter(organization=active_org).order_by("status", "-created_at")
        organization_name = active_org.name
    else:
        # Fallback to all if no org (shouldn't happen for admins)
        caregivers = Caregiver.objects.all().order_by("status", "-created_at")
        clients = Client.objects.all().order_by("status", "-created_at")
        organization_name = ""

    full_name = request.user.get_full_name().strip() or request.user.username

    return render(request, "registry/admin_dashboard.html", {
        "caregivers": caregivers,
        "clients": clients,
        "pending_caregivers": caregivers.filter(status="pending").count(),
        "pending_clients": clients.filter(status="pending").count(),
        "approved_caregivers": caregivers.filter(status="approved").count(),
        "approved_clients": clients.filter(status="approved").count(),
        "admin_display_name": full_name,
        "admin_organization_name": organization_name,
    })


@login_required
def caregiver_detail(request, pk):
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    caregiver = get_object_or_404(Caregiver, pk=pk)

    return render(request, "registry/caregiver_detail.html", {
        "caregiver": caregiver
    })


@login_required
def client_detail(request, pk):
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    client = get_object_or_404(Client, pk=pk)

    return render(request, "registry/client_detail.html", {
        "client": client
    })


@login_required
def update_caregiver_status(request, pk, status):
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    caregiver = get_object_or_404(Caregiver, pk=pk)

    # Status updates are state-changing operations, so only allow POST.
    if request.method != "POST":
        return redirect("caregiver_detail", pk=pk)

    if status not in ALLOWED_STATUSES:
        messages.error(request, "Invalid status.")
        return redirect("caregiver_detail", pk=pk)

    # If approving, create User account and all profiles
    if status == "approved" and caregiver.status != "approved":
        try:
            result = approve_caregiver_application(caregiver)
            messages.success(
                request, 
                f"{caregiver.name} was approved and user account created for {result['user'].email}."
            )
        except Exception as e:
            messages.error(request, f"Error approving application: {str(e)}")
            return redirect("caregiver_detail", pk=pk)
    else:
        # For rejected or other status changes, just update the status
        caregiver.status = status
        caregiver.save()
        messages.success(request, f"{caregiver.name} was marked as {status}.")

    return redirect("caregiver_detail", pk=pk)


@login_required
def update_client_status(request, pk, status):
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    client = get_object_or_404(Client, pk=pk)

    # Status updates are state-changing operations, so only allow POST.
    if request.method != "POST":
        return redirect("client_detail", pk=pk)

    if status not in ALLOWED_STATUSES:
        messages.error(request, "Invalid status.")
        return redirect("client_detail", pk=pk)

    # If approving, create User account and all profiles
    if status == "approved" and client.status != "approved":
        try:
            result = approve_client_application(client)
            messages.success(
                request, 
                f"{client.name} was approved and user account created for {result['user'].email}."
            )
        except Exception as e:
            messages.error(request, f"Error approving application: {str(e)}")
            return redirect("client_detail", pk=pk)
    else:
        # For rejected or other status changes, just update the status
        client.status = status
        client.save()
        messages.success(request, f"{client.name} was marked as {status}.")

    return redirect("client_detail", pk=pk)


@login_required
def switch_organization(request, org_id):
    """Switch the active organization in the user's session."""
    success = set_active_organization(request, org_id)
    
    if success:
        messages.success(request, "Organization switched successfully.")
    else:
        messages.error(request, "You do not have access to that organization.")
    
    return redirect("dashboard_redirect")
