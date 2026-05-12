from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib import messages


from .forms import (
    CaregiverApplicationForm,
    ClientApplicationForm
)

from .models import (
    Caregiver,
    Client
)


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
    profile = request.user.profile

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
    return render(request, "registry/admin_dashboard.html")