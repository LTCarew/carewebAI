from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from organizations.models import OrganizationStaff

from .forms import OrganizationAdminSignupForm
from .models import UserProfile, StaffProfile

def organization_signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard_redirect")

    if request.method == "POST":
        form = OrganizationAdminSignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()

                # Create UserProfile with new structure
                user_profile = UserProfile.objects.create(
                    user=user,
                    phone='',  # Can be added to form if needed
                )

                # Create StaffProfile
                staff_profile = StaffProfile.objects.create(
                    user_profile=user_profile,
                    title="Administrator"
                )

                # Now create the organization with staff_profile as primary_admin
                from organizations.models import Organization
                organization = Organization.objects.create(
                    name=form.cleaned_data["organization_name"],
                    city=form.cleaned_data["organization_city"],
                    zip_code=form.cleaned_data.get("organization_zip_code", ""),
                    contact_email=form.cleaned_data.get("organization_contact_email", ""),
                    primary_admin=staff_profile,
                )

                # Create OrganizationStaff relationship
                OrganizationStaff.objects.create(
                    organization=organization,
                    staff_profile=staff_profile,
                    role="admin",
                    status="active",
                    can_view_dashboard=True,
                    can_approve_applications=True,
                    can_invite_staff=True,
                    accepted_at=timezone.now(),
                    start_date=timezone.now().date(),
                )

            login(request, user)
            messages.success(request, "Organization setup complete. Welcome!")
            return redirect("org_dashboard")
    else:
        form = OrganizationAdminSignupForm()

    return render(
        request,
        "registration/organization_signup.html",
        {"form": form},
    )
