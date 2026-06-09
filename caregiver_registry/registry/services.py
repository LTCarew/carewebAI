"""
Service functions for handling application approval workflow.
Creates User accounts, profiles, and organization memberships.
"""
from django.contrib.auth import get_user_model
from django.db import transaction

from accounts.models import UserProfile
from organizations.models import OrganizationMembership
from .models import CaregiverProfile, ClientProfile


User = get_user_model()


def get_or_create_user_from_application(email, name):
    """
    Get existing user by email or create a new one.
    Username is set to email address.
    
    Args:
        email: User's email address
        name: User's full name
    
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


@transaction.atomic
def approve_caregiver_application(caregiver_app):
    """
    Approve a caregiver application and create all necessary records:
    - User account (if doesn't exist)
    - UserProfile
    - OrganizationMembership with role='caregiver'
    - CaregiverProfile
    
    Args:
        caregiver_app: Caregiver application instance
    
    Returns:
        dict with created/updated instances
    """
    # 1. Get or create User
    user = get_or_create_user_from_application(
        email=caregiver_app.email,
        name=caregiver_app.name
    )
    
    # 2. Create or update UserProfile
    profile, _ = UserProfile.objects.update_or_create(
        user=user,
        defaults={
            'name': caregiver_app.name,
            'phone': caregiver_app.phone,
            'email': caregiver_app.email,
            'pronouns': caregiver_app.pronouns,
            'contact_preferences': caregiver_app.contact_preferences,
        }
    )
    
    # 3. Create or update OrganizationMembership
    membership, _ = OrganizationMembership.objects.update_or_create(
        user=user,
        organization=caregiver_app.organization,
        role='caregiver',
        defaults={
            'status': 'active',
        }
    )
    
    # 4. Create or update CaregiverProfile
    caregiver_profile, _ = CaregiverProfile.objects.update_or_create(
        user=user,
        defaults={
            'base_zip_code': caregiver_app.base_zip_code,
            'willing_to_work_cities': caregiver_app.willing_to_work_cities,
            'transportation': caregiver_app.transportation,
            'availability': caregiver_app.availability,
            'hours_looking_for': caregiver_app.hours_looking_for,
            'certified_ihss_worker': caregiver_app.certified_ihss_worker,
            'additional_certifications': caregiver_app.additional_certifications,
            'experience_with': caregiver_app.experience_with,
            'languages_spoken': caregiver_app.languages_spoken,
            'pathogen_protocols': caregiver_app.pathogen_protocols,
            'rate': caregiver_app.rate,
            'bio': caregiver_app.bio,
            'wants_training_updates': caregiver_app.wants_training_updates,
        }
    )
    
    # 5. Update application status
    caregiver_app.status = 'approved'
    caregiver_app.profile_completed = True
    caregiver_app.save()
    
    return {
        'user': user,
        'profile': profile,
        'membership': membership,
        'caregiver_profile': caregiver_profile,
    }


@transaction.atomic
def approve_client_application(client_app):
    """
    Approve a client application and create all necessary records:
    - User account (if doesn't exist)
    - UserProfile
    - OrganizationMembership with role='client'
    - ClientProfile
    
    Args:
        client_app: Client application instance
    
    Returns:
        dict with created/updated instances
    """
    # 1. Get or create User
    user = get_or_create_user_from_application(
        email=client_app.email,
        name=client_app.name
    )
    
    # 2. Create or update UserProfile
    profile, _ = UserProfile.objects.update_or_create(
        user=user,
        defaults={
            'name': client_app.name,
            'phone': client_app.phone,
            'email': client_app.email,
            'pronouns': client_app.pronouns,
            'contact_preferences': client_app.contact_preferences,
            'address': client_app.address,  # Clients typically have address
        }
    )
    
    # 3. Create or update OrganizationMembership
    membership, _ = OrganizationMembership.objects.update_or_create(
        user=user,
        organization=client_app.organization,
        role='client',
        defaults={
            'status': 'active',
        }
    )
    
    # 4. Create or update ClientProfile
    client_profile, _ = ClientProfile.objects.update_or_create(
        user=user,
        defaults={
            'address': client_app.address,
            'base_zip_code': client_app.base_zip_code,
            'attendant_care_programs': client_app.attendant_care_programs,
            'languages_preferred': client_app.languages_preferred,
            'availability': client_app.availability,
            'schedule_flexibility': client_app.schedule_flexibility,
            'hours_per_week': client_app.hours_per_week,
            'care_needs': client_app.care_needs,
            'additional_care_needs': client_app.additional_care_needs,
            'preferences': client_app.preferences,
            'pathogen_protocol_preferences': client_app.pathogen_protocol_preferences,
        }
    )
    
    # 5. Update application status
    client_app.status = 'approved'
    client_app.profile_completed = True
    client_app.save()
    
    return {
        'user': user,
        'profile': profile,
        'membership': membership,
        'client_profile': client_profile,
    }


def user_has_role(user, organization, role):
    """
    Check if a user has a specific role in an organization.
    
    Args:
        user: User instance
        organization: Organization instance
        role: Role string ('admin', 'staff', 'caregiver', 'client')
    
    Returns:
        bool: True if user has the role, False otherwise
    """
    return OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        role=role,
        status='active'
    ).exists()


def get_user_memberships(user, organization=None):
    """
    Get all organization memberships for a user.
    
    Args:
        user: User instance
        organization: Optional Organization instance to filter by
    
    Returns:
        QuerySet of OrganizationMembership instances
    """
    memberships = OrganizationMembership.objects.filter(
        user=user,
        status='active'
    ).select_related('organization')
    
    if organization:
        memberships = memberships.filter(organization=organization)
    
    return memberships


def get_active_organization(request):
    """
    Get the currently active organization from session.
    Defaults to the first organization membership if not set.
    
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
        # Verify user still has access to this org
        membership = OrganizationMembership.objects.filter(
            user=user,
            organization_id=org_id,
            status='active'
        ).select_related('organization').first()
        
        if membership:
            return membership.organization
    
    # Default to first membership
    first_membership = OrganizationMembership.objects.filter(
        user=user,
        status='active'
    ).select_related('organization').first()
    
    if first_membership:
        # Store in session for next time
        request.session['active_organization_id'] = first_membership.organization.id
        return first_membership.organization
    
    return None


def set_active_organization(request, org_id):
    """
    Set the active organization in the user's session.
    
    Args:
        request: Django request object
        org_id: Organization ID to set as active
    
    Returns:
        bool: True if successful, False if user doesn't have access
    """
    user = request.user
    
    if not user.is_authenticated:
        return False
    
    # Verify user has access to this organization
    has_access = OrganizationMembership.objects.filter(
        user=user,
        organization_id=org_id,
        status='active'
    ).exists()
    
    if has_access:
        request.session['active_organization_id'] = org_id
        return True
    
    return False


def get_user_role_in_organization(user, organization):
    """
    Get the user's primary role in a specific organization.
    If user has multiple roles, prioritizes: admin > staff > caregiver > client
    
    Args:
        user: User instance
        organization: Organization instance
    
    Returns:
        str: Role name or None
    """
    memberships = OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        status='active'
    ).values_list('role', flat=True)
    
    role_priority = ['admin', 'staff', 'caregiver', 'client']
    
    for role in role_priority:
        if role in memberships:
            return role
    
    return None
