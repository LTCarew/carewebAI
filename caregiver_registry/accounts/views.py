from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.shortcuts import redirect, render

from organizations.models import OrganizationStaff

from .forms import OrganizationAdminSignupForm
from .models import UserProfile

def organization_signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard_redirect")

    if request.method == "POST":
        form = OrganizationAdminSignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user, organization = form.save()

                UserProfile.objects.create(
                    user=user,
                    organization=organization,
                    user_type="admin_staff",
                )

                OrganizationStaff.objects.create(
                    organization=organization,
                    user=user,
                    role="admin",
                    can_view_dashboard=True,
                    can_approve_applications=True,
                    can_invite_staff=True,
                )

            login(request, user)
            messages.success(request, "Organization setup complete. Welcome!")
            return redirect("admin_dashboard")
    else:
        form = OrganizationAdminSignupForm()

    return render(
        request,
        "registration/organization_signup.html",
        {"form": form},
    )
