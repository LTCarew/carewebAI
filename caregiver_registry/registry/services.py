"""
Service functions for the registry app.
Handles profile creation, approval workflows, and membership queries.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from organizations.models import OrganizationStaff
from .models import (
    CaregiverProfile,
    ClientProfile,
    OrganizationCaregiver,
    OrganizationClient,
)


User = get_user_model()


def get_or_create_user_from_email(email, name=""):
    """
    Get existing user by email or create a new one.
    Username is set to email address.
    
    Args:
        email: User's email address
        name: User's full name (optional)
    
    Returns:
        User instance
    """
    user, created = User.objects.get_or_create(
        email=email.lower(),
        defaults={
            'username': email.lower(),
            'email': email.lower(),
        }
    )
    
    if created:
        # Set an unusable password - user will need to reset via email
        user.set_unusable_password()
        user.save()
    
    return user


def get_user_staff_role(user, organization):
    """
    Get the user's staff role in a specific organization.
    
    Args:
        user: User instance
        organization: Organization instance
    
    Returns:
        OrganizationStaff instance or None
    """
    try:
        user_profile = user.profile
        if hasattr(user_profile, 'staff_profile'):
            return OrganizationStaff.objects.filter(
                staff_profile=user_profile.staff_profile,
                organization=organization,
                status='active'
            ).first()
    except (UserProfile.DoesNotExist, AttributeError):
        pass
    return None


def get_user_caregiver_relationship(user, organization):
    """
    Get the user's caregiver relationship with an organization.
    
    Args:
        user: User instance
        organization: Organization instance
    
    Returns:
        OrganizationCaregiver instance or None
    """
    try:
        user_profile = user.profile
        if hasattr(user_profile, 'caregiver_profile'):
            return OrganizationCaregiver.objects.filter(
                caregiver_profile=user_profile.caregiver_profile,
                organization=organization
            ).first()
    except (UserProfile.DoesNotExist, AttributeError):
        pass
    return None


def get_user_client_relationship(user, organization):
    """
    Get the user's client relationship with an organization.
    
    Args:
        user: User instance
        organization: Organization instance
    
    Returns:
        OrganizationClient instance or None
    """
    try:
        user_profile = user.profile
        if hasattr(user_profile, 'client_profile'):
            return OrganizationClient.objects.filter(
                client_profile=user_profile.client_profile,
                organization=organization
            ).first()
    except (UserProfile.DoesNotExist, AttributeError):
        pass
    return None


def get_user_primary_role(user, organization):
    """
    Get the user's primary role in a specific organization.
    Priority: staff/admin > caregiver > client
    
    Args:
        user: User instance
        organization: Organization instance
    
    Returns:
        str: 'admin', 'staff', 'caregiver', 'client', or None
    """
    # Check staff role first
    staff = get_user_staff_role(user, organization)
    if staff:
        return staff.role  # 'admin' or 'staff'
    
    # Check caregiver
    caregiver_rel = get_user_caregiver_relationship(user, organization)
    if caregiver_rel and caregiver_rel.status == 'approved':
        return 'caregiver'
    
    # Check client
    client_rel = get_user_client_relationship(user, organization)
    if client_rel and client_rel.status == 'approved':
        return 'client'
    
    return None


def get_active_organization(request):
    """
    Get the currently active organization from session.
    Defaults to the first organization the user has access to.
    
    Args:
        request: Django request object
    
    Returns:
        Organization instance or None
    """
    user = request.user
    
    if not user.is_authenticated:
        return None
    
    # Try to get from session
    org_id = request.session.get('active_organization_id')
    
    if org_id:
        from organizations.models import Organization
        # Check if user has access to this organization
        try:
            org = Organization.objects.get(id=org_id)
            if user_has_access_to_organization(user, org):
                return org
        except Organization.DoesNotExist:
            pass
    
    # Default to first organization user has access to
    orgs = get_user_organizations(user)
    if orgs:
        first_org = orgs[0]
        request.session['active_organization_id'] = first_org.id
        return first_org
    
    return None


def user_has_access_to_organization(user, organization):
    """
    Check if user has any relationship with an organization.
    
    Args:
        user: User instance
        organization: Organization instance
    
    Returns:
        bool: True if user has access
    """
    # Check staff
    if get_user_staff_role(user, organization):
        return True
    
    # Check caregiver
    if get_user_caregiver_relationship(user, organization):
        return True
    
    # Check client
    if get_user_client_relationship(user, organization):
        return True
    
    return False


# ==============================================
# Support Coordinator Helper Functions
# ==============================================

def get_coordinator_clients(coordinator_profile):
    """
    Get all clients that a support coordinator is assisting.
    
    Args:
        coordinator_profile: SupportCoordinatorProfile instance
    
    Returns:
        QuerySet of ClientCoordinator instances (active relationships)
    """
    from .models import ClientCoordinator
    
    return ClientCoordinator.objects.filter(
        coordinator_profile=coordinator_profile,
        status='active'
    ).select_related(
        'client_profile__user_profile'
    ).order_by('-created_at')


def get_client_coordinators(client_profile):
    """
    Get all support coordinators for a client.
    
    Args:
        client_profile: ClientProfile instance
    
    Returns:
        QuerySet of ClientCoordinator instances
    """
    from .models import ClientCoordinator
    
    return ClientCoordinator.objects.filter(
        client_profile=client_profile
    ).select_related(
        'coordinator_profile__user_profile'
    ).order_by('-created_at')


def coordinator_can_edit(client_coordinator):
    """
    Check if a coordinator has permission to edit a client's profile.
    
    Args:
        client_coordinator: ClientCoordinator instance
    
    Returns:
        bool: True if coordinator can edit
    """
    return (
        client_coordinator.status == 'active' and 
        client_coordinator.can_edit_profile
    )


def coordinator_can_approve(client_coordinator):
    """
    Check if a coordinator has permission to approve caregivers for a client.
    
    Args:
        client_coordinator: ClientCoordinator instance
    
    Returns:
        bool: True if coordinator can approve caregivers
    """
    return (
        client_coordinator.status == 'active' and 
        client_coordinator.can_approve_caregivers
    )


def send_coordinator_invite(client_profile, email, invited_by_user):
    """
    Create a coordinator invitation and send email.
    
    Args:
        client_profile: ClientProfile instance
        email: Email address to send invitation to
        invited_by_user: User instance who is sending the invite
    
    Returns:
        CoordinatorInvite instance
    """
    from .models import CoordinatorInvite
    from django.core.mail import send_mail
    from django.conf import settings
    from django.urls import reverse
    
    # Create the invitation
    invite = CoordinatorInvite.objects.create(
        client_profile=client_profile,
        email=email,
        invited_by=invited_by_user.profile
    )
    
    # Build the signup URL with token
    signup_url = f"{settings.SITE_URL}{reverse('coordinator_signup', kwargs={'token': invite.token})}"
    
    # Send email
    subject = f"Invitation to be a Support Coordinator for {client_profile.user_profile.name}"
    message = f"""
Hello,

{client_profile.user_profile.name} has invited you to be their Support Coordinator on CareWeb AI.

As a Support Coordinator, you can help manage care needs and assist with finding caregivers.

To accept this invitation and create your account, please click the link below:

{signup_url}

This invitation will expire in 7 days.

If you have any questions, please contact us.

Best regards,
The CareWeb AI Team
    """.strip()
    
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
    
    return invite


def get_user_coordinator_role(user):
    """
    Check if user is a support coordinator and return their profile if so.
    
    Args:
        user: User instance
    
    Returns:
        SupportCoordinatorProfile instance or None
    """
    try:
        user_profile = user.profile
        if hasattr(user_profile, 'support_coordinator_profile'):
            return user_profile.support_coordinator_profile
    except (UserProfile.DoesNotExist, AttributeError):
        pass
    return None


def get_user_organizations(user):
    """
    Get all organizations the user has access to.
    
    Args:
        user: User instance
    
    Returns:
        QuerySet of Organization instances
    """
    from organizations.models import Organization
    
    if not user.is_authenticated:
        return Organization.objects.none()
    
    try:
        user_profile = user.profile
    except UserProfile.DoesNotExist:
        return Organization.objects.none()
    
    org_ids = set()
    
    # Staff organizations
    if hasattr(user_profile, 'staff_profile'):
        staff_orgs = OrganizationStaff.objects.filter(
            staff_profile=user_profile.staff_profile,
            status='active'
        ).values_list('organization_id', flat=True)
        org_ids.update(staff_orgs)
    
    # Caregiver organizations
    if hasattr(user_profile, 'caregiver_profile'):
        caregiver_orgs = OrganizationCaregiver.objects.filter(
            caregiver_profile=user_profile.caregiver_profile,
            status__in=['pending', 'approved']
        ).values_list('organization_id', flat=True)
        org_ids.update(caregiver_orgs)
    
    # Client organizations
    if hasattr(user_profile, 'client_profile'):
        client_orgs = OrganizationClient.objects.filter(
            client_profile=user_profile.client_profile,
            status__in=['pending', 'approved']
        ).values_list('organization_id', flat=True)
        org_ids.update(client_orgs)
    
    return Organization.objects.filter(id__in=org_ids)


@transaction.atomic
def approve_caregiver(org_caregiver, approved_by_user):
    """
    Approve a caregiver's application to join an organization.
    Activates the user account and sends approval email.
    
    Args:
        org_caregiver: OrganizationCaregiver instance
        approved_by_user: User instance who is approving
    
    Returns:
        OrganizationCaregiver instance (updated)
    """
    org_caregiver.status = 'approved'
    org_caregiver.approved_at = timezone.now()
    
    try:
        org_caregiver.approved_by = approved_by_user.profile
    except UserProfile.DoesNotExist:
        pass
    
    org_caregiver.save()
    
    # Activate user account (allow login)
    user = org_caregiver.caregiver_profile.user_profile.user
    user.is_active = True
    user.save()
    
    # Send approval email
    send_approval_email(org_caregiver)
    
    return org_caregiver


@transaction.atomic
def approve_client(org_client, approved_by_user):
    """
    Approve a client's application to join an organization.
    Activates the user account and sends approval email.
    
    Args:
        org_client: OrganizationClient instance
        approved_by_user: User instance who is approving
    
    Returns:
        OrganizationClient instance (updated)
    """
    org_client.status = 'approved'
    org_client.approved_at = timezone.now()
    
    try:
        org_client.approved_by = approved_by_user.profile
    except UserProfile.DoesNotExist:
        pass
    
    org_client.save()
    
    # Activate user account (allow login)
    user = org_client.client_profile.user_profile.user
    user.is_active = True
    user.save()
    
    # Send approval email
    send_approval_email(org_client)
    
    return org_client


def send_approval_email(org_relationship):
    """
    Send email when user is approved by an organization.
    Notifies them they can now login.
    
    Args:
        org_relationship: OrganizationCaregiver or OrganizationClient instance
    """
    from django.core.mail import send_mail
    from django.conf import settings
    from django.template.loader import render_to_string
    
    # Determine if this is a caregiver or client
    is_caregiver = isinstance(org_relationship, OrganizationCaregiver)
    
    if is_caregiver:
        user_profile = org_relationship.caregiver_profile.user_profile
        role_name = "Caregiver"
    else:
        user_profile = org_relationship.client_profile.user_profile
        role_name = "Client"
    
    user = user_profile.user
    organization = org_relationship.organization
    
    # Build the login URL
    login_url = f"{settings.SITE_URL}/accounts/login/"
    
    # Email subject
    subject = f"Your {role_name} Application Has Been Approved - CareWeb AI"
    
    # Email body
    message = f"""Hello {user_profile.name},

Great news! {organization.name} has approved your {role_name.lower()} application on CareWeb AI.

You can now login to your account and access the caregiver/client registry:

Login URL: {login_url}
Username: {user.username}

Once logged in, you'll be able to:
- View your dashboard
- Browse the {"client" if is_caregiver else "caregiver"} registry
- Connect with potential {"clients" if is_caregiver else "caregivers"}

Welcome to the CareWeb AI network!

Best regards,
The CareWeb AI Team
""".strip()
    
    # Send the email
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user_profile.email],
        fail_silently=False,
    )


def user_is_admin_or_staff(user):
    """
    Check if user has admin or staff role in any organization.
    
    Args:
        user: User instance
    
    Returns:
        bool: True if user is admin or staff
    """
    if not user.is_authenticated:
        return False
    
    try:
        user_profile = user.profile
        if hasattr(user_profile, 'staff_profile'):
            return OrganizationStaff.objects.filter(
                staff_profile=user_profile.staff_profile,
                role__in=['admin', 'staff'],
                status='active'
            ).exists()
    except UserProfile.DoesNotExist:
        pass
    
    return False
