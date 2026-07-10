"""
Shared fixture builder helpers for all Django TestCase tests.

Usage:
    from tests_helpers import (
        make_org_admin, make_caregiver_user, make_client_user,
        make_coordinator_user, make_match,
    )
"""
from django.contrib.auth import get_user_model
from accounts.models import UserProfile, StaffProfile
from organizations.models import Organization, OrganizationStaff
from registry.models import (
    CaregiverProfile, ClientProfile,
    OrganizationCaregiver, OrganizationClient,
    SupportCoordinatorProfile, ClientCoordinator, CoordinatorInvite,
    Schedule, ScheduleEntry,
)
from matching.models import Match

User = get_user_model()

# ──────────────────────────────────────────────────────────────────────────────
# Low-level user builders
# ──────────────────────────────────────────────────────────────────────────────

def _make_user(username, password="TestPass123!", is_active=True, email=None):
    email = email or f"{username}@test.example"
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name="Test",
        last_name=username.title(),
        is_active=is_active,
    )
    return user


def _make_profile(user, address=""):
    return UserProfile.objects.create(
        user=user,
        phone="555-0100",
        contact_preferences=["email"],
        address=address,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Organization + admin/staff
# ──────────────────────────────────────────────────────────────────────────────

def make_org_admin(username="orgadmin", org_name="Test Org"):
    """Create a full org-admin user stack and return (user, org, staff_profile, org_staff)."""
    user = _make_user(username)
    profile = _make_profile(user)
    staff_profile = StaffProfile.objects.create(user_profile=profile)
    org = Organization.objects.create(
        name=org_name,
        city="Testville",
        zip_code="90210",
        primary_admin=staff_profile,
    )
    org_staff = OrganizationStaff.objects.create(
        organization=org,
        staff_profile=staff_profile,
        role="admin",
        status="active",
        can_approve_applications=True,
    )
    return user, org, staff_profile, org_staff


def make_staff_user(org, username="staffuser"):
    """Create a staff user attached to an existing org. Returns (user, staff_profile, org_staff)."""
    user = _make_user(username)
    profile = _make_profile(user)
    staff_profile = StaffProfile.objects.create(user_profile=profile)
    org_staff = OrganizationStaff.objects.create(
        organization=org,
        staff_profile=staff_profile,
        role="staff",
        status="active",
        can_approve_applications=True,
    )
    return user, staff_profile, org_staff


# ──────────────────────────────────────────────────────────────────────────────
# Caregiver
# ──────────────────────────────────────────────────────────────────────────────

def make_caregiver_user(username="caregiver1", is_active=True):
    """Create a caregiver user stack. Returns (user, caregiver_profile)."""
    user = _make_user(username, is_active=is_active)
    profile = _make_profile(user)
    caregiver_profile = CaregiverProfile.objects.create(
        user_profile=profile,
        base_zip_code="90210",
        rate="15_20",
        hours_looking_for="part_time",
        availability={"monday": ["morning"]},
    )
    return user, caregiver_profile


def add_caregiver_to_org(caregiver_profile, org, status="approved"):
    """Create OrganizationCaregiver relationship. Returns the relationship object."""
    return OrganizationCaregiver.objects.create(
        organization=org,
        caregiver_profile=caregiver_profile,
        status=status,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Client
# ──────────────────────────────────────────────────────────────────────────────

def make_client_user(username="client1", is_active=True):
    """Create a client user stack. Returns (user, client_profile)."""
    user = _make_user(username, is_active=is_active)
    profile = _make_profile(user, address="123 Test St")
    client_profile = ClientProfile.objects.create(
        user_profile=profile,
        base_zip_code="90210",
        availability={"monday": ["morning"]},
        care_needs=["bathing"],
    )
    return user, client_profile


def add_client_to_org(client_profile, org, status="approved"):
    """Create OrganizationClient relationship. Returns the relationship object."""
    return OrganizationClient.objects.create(
        organization=org,
        client_profile=client_profile,
        status=status,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Support coordinator
# ──────────────────────────────────────────────────────────────────────────────

def make_coordinator_user(username="coordinator1"):
    """Create a support coordinator user stack. Returns (user, coordinator_profile)."""
    user = _make_user(username)
    profile = _make_profile(user)
    coordinator_profile = SupportCoordinatorProfile.objects.create(
        user_profile=profile,
        relationship_to_clients="Friend",
    )
    return user, coordinator_profile


def link_coordinator_to_client(coordinator_profile, client_profile, invited_by_profile=None):
    """Create ClientCoordinator link. Returns the ClientCoordinator."""
    from django.utils import timezone
    return ClientCoordinator.objects.create(
        client_profile=client_profile,
        coordinator_profile=coordinator_profile,
        status="active",
        invited_by=invited_by_profile,
        accepted_at=timezone.now(),
    )


def make_coordinator_invite(client_profile, invited_by_profile, email="coord@test.example"):
    """Create a fresh, unused, unexpired CoordinatorInvite."""
    return CoordinatorInvite.objects.create(
        client_profile=client_profile,
        invited_by=invited_by_profile,
        email=email,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Match
# ──────────────────────────────────────────────────────────────────────────────

def make_match(caregiver_profile, client_profile, organization=None,
               initiated_by="caregiver",
               caregiver_status="approved", client_status="pending",
               overall_status=None):
    """
    Create a Match with explicit statuses. Defaults to caregiver-initiated pending match.
    Pass overall_status=None to let it be computed from caregiver/client statuses.
    ``organization`` is required by the Match model; if omitted the first org in the
    DB is used (convenient for tests that already created one via make_org_admin).
    """
    from organizations.models import Organization as Org
    if organization is None:
        organization = Org.objects.first()
        if organization is None:
            raise ValueError(
                "make_match: no organization provided and none exist in the DB. "
                "Call make_org_admin() before make_match(), or pass organization=<org>."
            )
    if overall_status is None:
        if caregiver_status == "approved" and client_status == "approved":
            overall_status = "active"
        elif caregiver_status in ("declined", "cancelled") or client_status in ("declined", "cancelled"):
            overall_status = "cancelled"
        else:
            overall_status = "pending"
    return Match.objects.create(
        organization=organization,
        caregiver=caregiver_profile,
        client=client_profile,
        initiated_by=initiated_by,
        caregiver_status=caregiver_status,
        client_status=client_status,
        status=overall_status,
        match_score=75,
        ai_reasoning="test match",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Schedule helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_schedule(client_profile, caregiver_profile, status="draft", match=None,
                  organization=None):
    """
    Create a Schedule for the given client/caregiver. Returns the Schedule.
    ``organization`` is required by the model; if omitted the first org in the DB
    is used (same convention as make_match).
    """
    from organizations.models import Organization as Org
    if organization is None:
        organization = Org.objects.first()
        if organization is None:
            raise ValueError(
                "make_schedule: no organization provided and none exist in the DB. "
                "Call make_org_admin() before make_schedule()."
            )
    return Schedule.objects.create(
        organization=organization,
        client=client_profile,
        caregiver=caregiver_profile,
        match=match,
        status=status,
        notes="Test schedule notes",
    )


def make_schedule_entry(schedule, day="monday", start="09:00", end="12:00"):
    """Create a ScheduleEntry attached to the schedule."""
    return ScheduleEntry.objects.create(
        schedule=schedule,
        day_of_week=day,
        start_time=start,
        end_time=end,
    )
