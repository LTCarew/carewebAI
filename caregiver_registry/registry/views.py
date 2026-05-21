"""Registry views for application intake, dashboards, and admin review workflow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CaregiverApplicationForm, ClientApplicationForm
from .models import Caregiver, Client


# Keep statuses centralized so update views cannot drift apart.
ALLOWED_STATUSES = ["pending", "approved", "rejected"]


def _user_is_admin_staff(user):
    """Return True when the authenticated user has the admin_staff role."""
    profile = getattr(user, "profile", None)
    return bool(profile and profile.user_type == "admin_staff")


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
    # Use safe attribute lookup so users without profiles do not trigger exceptions.
    profile = getattr(request.user, "profile", None)

    if not profile:
        messages.warning(request, "Your account is missing a role profile. Please contact support.")
        return redirect("home")

    if profile.user_type == "caregiver":
        return redirect("caregiver_dashboard")

    if profile.user_type == "client":
        return redirect("client_dashboard")

    if profile.user_type == "admin_staff":
        return redirect("admin_dashboard")

    return redirect("home")


@login_required
def caregiver_dashboard(request):
    return render(request, "registry/caregiver_dashboard.html")


@login_required
def client_dashboard(request):
    return render(request, "registry/client_dashboard.html")


@login_required
def admin_dashboard(request):
    unauthorized_redirect = _redirect_if_not_admin_staff(request)
    if unauthorized_redirect:
        return unauthorized_redirect

    caregivers = Caregiver.objects.all().order_by("status", "-created_at")
    clients = Client.objects.all().order_by("status", "-created_at")

    return render(request, "registry/admin_dashboard.html", {
        "caregivers": caregivers,
        "clients": clients,
        "pending_caregivers": caregivers.filter(status="pending").count(),
        "pending_clients": clients.filter(status="pending").count(),
        "approved_caregivers": caregivers.filter(status="approved").count(),
        "approved_clients": clients.filter(status="approved").count(),
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

    client.status = status
    client.save()

    messages.success(request, f"{client.name} was marked as {status}.")
    return redirect("client_detail", pk=pk)