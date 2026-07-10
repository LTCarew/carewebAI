from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from organizations.models import OrganizationStaff, OrganizationStaffInvite

from .forms import OrganizationAdminSignupForm, StaffInviteForm, StaffSignupForm
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


# ==============================================
# Staff Invite View (admin/staff sends invite)
# ==============================================

@login_required
def staff_invite_send(request):
    """
    Allow an org admin (or staff with can_invite_staff) to invite a new staff
    member.  Creates an OrganizationStaffInvite and sends an email with a
    unique token link.
    """
    from registry.services import get_active_organization, get_user_primary_role, send_staff_invite

    active_org = get_active_organization(request)
    if not active_org:
        messages.error(request, "No active organization found.")
        return redirect("org_dashboard")

    # Only admins, or staff with can_invite_staff permission, may invite
    try:
        org_staff = OrganizationStaff.objects.get(
            staff_profile=request.user.profile.staff_profile,
            organization=active_org,
            status="active",
        )
    except (OrganizationStaff.DoesNotExist, AttributeError):
        messages.error(request, "You do not have permission to invite staff.")
        return redirect("org_dashboard")

    if org_staff.role != "admin" and not org_staff.can_invite_staff:
        messages.error(request, "You do not have permission to invite staff.")
        return redirect("org_dashboard")

    if request.method == "POST":
        form = StaffInviteForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            role = form.cleaned_data["role"]
            can_approve = form.cleaned_data.get("can_approve_applications", False)
            can_invite = form.cleaned_data.get("can_invite_staff", False)

            try:
                invite = send_staff_invite(
                    organization=active_org,
                    email=email,
                    role=role,
                    invited_by_user=request.user,
                    can_approve_applications=can_approve,
                    can_invite_staff=can_invite,
                )
                messages.success(
                    request,
                    f"Invitation sent to {email}. They will receive an email with signup instructions.",
                )
            except Exception as e:
                messages.error(request, f"Error sending invitation: {str(e)}")

            return redirect("org_dashboard")
    else:
        form = StaffInviteForm()

    return render(request, "registry/staff_invite.html", {
        "form": form,
        "organization": active_org,
    })


# ==============================================
# Staff Signup View (invited staff accepts)
# ==============================================

def staff_signup(request, token):
    """
    Public view for an invited staff member to accept their invitation.
    Creates their user account, UserProfile, StaffProfile, and
    OrganizationStaff records, then logs them in and redirects to the
    org dashboard.
    """
    invite = get_object_or_404(OrganizationStaffInvite, token=token)

    if not invite.is_valid():
        if invite.accepted:
            messages.warning(request, "This invitation has already been accepted.")
        elif invite.is_expired():
            messages.error(request, "This invitation link has expired.")
        else:
            messages.error(request, "This invitation is no longer valid.")
        return redirect("home")

    if request.method == "POST":
        form = StaffSignupForm(request.POST)
        if form.is_valid():
            org_staff, staff_user = form.save(invite)

            messages.success(
                request,
                f"Welcome! Your staff account for {invite.organization.name} "
                f"has been created. You are now logged in.",
            )

            # Set the active organization in session so the dashboard loads correctly
            login(request, staff_user, backend="django.contrib.auth.backends.ModelBackend")
            request.session["active_organization_id"] = invite.organization.id

            return redirect("org_dashboard")
    else:
        form = StaffSignupForm(initial={"email": invite.email})

    return render(request, "registry/staff_signup.html", {
        "form": form,
        "invite": invite,
    })
