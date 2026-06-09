from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.shortcuts import redirect, render

from organizations.models import OrganizationStaff, OrganizationMembership

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

                # Create UserProfile with new structure
                UserProfile.objects.create(
                    user=user,
                    name=user.get_full_name() or user.username,
                    email=user.email,
                    phone='',  # Can be added to form if needed
                )

                # Create OrganizationMembership for admin role
                OrganizationMembership.objects.create(
                    user=user,
                    organization=organization,
                    role='admin',
                    status='active',
                )

                # Keep OrganizationStaff for backward compatibility
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
