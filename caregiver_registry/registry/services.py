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
    return org_caregiver


@transaction.atomic
def approve_client(org_client, approved_by_user):
    """
    Approve a client's application to join an organization.
    
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
    return org_client


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
