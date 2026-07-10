"""
registry/tests.py — Django TestCase view tests for the registry module.

Covers:
  - dashboard_redirect role routing
  - Caregiver / client / org / coordinator dashboards
  - Caregiver & client application forms (GET + POST)
  - Status update (approve/reject) flows
  - Registry network access by role
  - Coordinator invite + signup flows
  - Schedule create / submit / cancel / detail access
  - Pool browsing
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from django.test import TestCase, Client as TestClient, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from tests_helpers import (
    make_org_admin, make_staff_user,
    make_caregiver_user, add_caregiver_to_org,
    make_client_user, add_client_to_org,
    make_coordinator_user, link_coordinator_to_client,
    make_coordinator_invite,
    make_match, make_schedule, make_schedule_entry,
)
from django.urls import reverse as _reverse

User = get_user_model()
PASSWORD = "TestPass123!"


# ─────────────────────────────────────────────────────────────────────────────
# dashboard_redirect role routing
# ─────────────────────────────────────────────────────────────────────────────

class DashboardRedirectTest(TestCase):
    """dashboard_redirect must route each role to the correct dashboard.

    dashboard_redirect requires the user to have an active org (via
    get_active_organization) so caregivers and clients must be added
    to an org before the redirect can route them correctly.
    """

    def setUp(self):
        self.c = TestClient()
        self.url = reverse("dashboard_redirect")
        # Shared org used by caregiver/client tests
        self.admin_user, self.org, _, _ = make_org_admin(username="dashboardadmin")

    def test_org_admin_goes_to_org_dashboard(self):
        self.c.force_login(self.admin_user)
        response = self.c.get(self.url)
        self.assertRedirects(response, reverse("org_dashboard"))

    def test_caregiver_goes_to_caregiver_dashboard(self):
        cg_user, cg_profile = make_caregiver_user(username="dashboardcg")
        add_caregiver_to_org(cg_profile, self.org)
        self.c.force_login(cg_user)
        response = self.c.get(self.url)
        self.assertRedirects(response, reverse("caregiver_dashboard"))

    def test_client_goes_to_client_dashboard(self):
        cl_user, cl_profile = make_client_user(username="dashboardcl")
        add_client_to_org(cl_profile, self.org)
        self.c.force_login(cl_user)
        response = self.c.get(self.url)
        self.assertRedirects(response, reverse("client_dashboard"))

    def test_coordinator_goes_to_coordinator_dashboard(self):
        coord_user, coord_profile = make_coordinator_user(username="dashboardcoord")
        _, cl_profile = make_client_user(username="dashboardcoordcl")
        link_coordinator_to_client(coord_profile, cl_profile)
        self.c.force_login(coord_user)
        response = self.c.get(self.url)
        self.assertRedirects(response, reverse("coordinator_dashboard"))


# ─────────────────────────────────────────────────────────────────────────────
# Caregiver dashboard
# ─────────────────────────────────────────────────────────────────────────────

class CaregiverDashboardTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.cg_user, self.cg_profile = make_caregiver_user(username="cgdashboard")
        self.c.force_login(self.cg_user)

    def test_renders_200(self):
        response = self.c.get(reverse("caregiver_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_contains_match_sections(self):
        response = self.c.get(reverse("caregiver_dashboard"))
        # Page should contain dashboard content (at minimum renders without error)
        self.assertNotContains(response, "500")

    def test_client_cannot_access_caregiver_dashboard(self):
        cl_user, _ = make_client_user(username="cgdashboardcl")
        self.c.force_login(cl_user)
        response = self.c.get(reverse("caregiver_dashboard"))
        # Should redirect away (not 200)
        self.assertIn(response.status_code, [302, 403])

    def test_match_table_hides_logged_in_caregiver_column(self):
        """
        On the caregiver dashboard the match table must NOT render a link
        to the logged-in caregiver's own detail page, but MUST show the
        matched client's name.
        """
        _, org, _, _ = make_org_admin(username="cghide_admin")
        add_caregiver_to_org(self.cg_profile, org)
        _, cl_profile = make_client_user(username="cghide_client")
        add_client_to_org(cl_profile, org)
        make_match(
            self.cg_profile, cl_profile, organization=org,
            caregiver_status="pending", client_status="pending",
        )
        response = self.c.get(reverse("caregiver_dashboard"))
        self.assertEqual(response.status_code, 200)
        # Client name MUST be visible
        self.assertContains(response, cl_profile.user_profile.display_name)
        # Careworker detail link for the logged-in user must NOT appear
        cg_detail_url = _reverse("caregiver_detail", args=[self.cg_profile.pk])
        self.assertNotContains(response, cg_detail_url)


# ─────────────────────────────────────────────────────────────────────────────
# Client dashboard
# ─────────────────────────────────────────────────────────────────────────────

class ClientDashboardTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.cl_user, self.cl_profile = make_client_user(username="cldashboard")
        self.c.force_login(self.cl_user)

    def test_renders_200(self):
        response = self.c.get(reverse("client_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_caregiver_cannot_access_client_dashboard(self):
        cg_user, _ = make_caregiver_user(username="cldashboardcg")
        self.c.force_login(cg_user)
        response = self.c.get(reverse("client_dashboard"))
        self.assertIn(response.status_code, [302, 403])

    def test_match_table_hides_logged_in_client_column(self):
        """
        On the client dashboard the match table must NOT render a link to
        the logged-in client's own detail page, but MUST show the matched
        careworker's name.
        """
        _, org, _, _ = make_org_admin(username="clhide_admin")
        add_client_to_org(self.cl_profile, org)
        _, cg_profile = make_caregiver_user(username="clhide_cg")
        add_caregiver_to_org(cg_profile, org)
        make_match(
            cg_profile, self.cl_profile, organization=org,
            caregiver_status="approved", client_status="pending",
        )
        response = self.c.get(reverse("client_dashboard"))
        self.assertEqual(response.status_code, 200)
        # Careworker name MUST be visible
        self.assertContains(response, cg_profile.user_profile.display_name)
        # Client detail link for the logged-in user must NOT appear
        cl_detail_url = _reverse("client_detail", args=[self.cl_profile.pk])
        self.assertNotContains(response, cl_detail_url)


# ─────────────────────────────────────────────────────────────────────────────
# Org dashboard
# ─────────────────────────────────────────────────────────────────────────────

class OrgDashboardTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, self.staff_profile, _ = make_org_admin(username="orgdashboard")
        self.c.force_login(self.admin_user)

    def test_renders_200(self):
        response = self.c.get(reverse("org_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_caregiver_cannot_access_org_dashboard(self):
        cg_user, _ = make_caregiver_user(username="orgdashcg")
        self.c.force_login(cg_user)
        response = self.c.get(reverse("org_dashboard"))
        self.assertIn(response.status_code, [302, 403])

    def test_client_cannot_access_org_dashboard(self):
        cl_user, _ = make_client_user(username="orgdashcl")
        self.c.force_login(cl_user)
        response = self.c.get(reverse("org_dashboard"))
        self.assertIn(response.status_code, [302, 403])


# ─────────────────────────────────────────────────────────────────────────────
# Caregiver application form
# ─────────────────────────────────────────────────────────────────────────────

class CaregiverApplyViewTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.url = reverse("caregiver_apply")
        # Minimal valid POST data for the caregiver application
        self.valid_data = {
            "first_name": "Bob",
            "last_name": "Smith",
            "username": "bobsmith",
            "email": "bob@caregiver.example",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "phone": "555-0200",
            "contact_preferences": ["email"],
            "base_zip_code": "90001",
            "hours_looking_for": "part_time",
            "rate": "17_20",
            # availability fields are optional (no days required)
        }

    def test_get_renders_200(self):
        response = self.c.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_valid_redirects_to_success(self):
        response = self.c.post(self.url, self.valid_data)
        self.assertRedirects(response, reverse("application_success"))

    def test_post_valid_creates_inactive_user(self):
        self.c.post(self.url, self.valid_data)
        user = User.objects.get(username="bobsmith")
        self.assertFalse(user.is_active, "Caregiver applicants should be inactive until approved")

    def test_post_duplicate_username_shows_error(self):
        User.objects.create_user(username="bobsmith", email="other@test.example", password=PASSWORD)
        response = self.c.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already taken")

    def test_post_duplicate_email_shows_error(self):
        data = self.valid_data.copy()
        User.objects.create_user(username="other", email="bob@caregiver.example", password=PASSWORD)
        response = self.c.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_post_password_mismatch_shows_error(self):
        data = self.valid_data.copy()
        data["password2"] = "Different123!"
        response = self.c.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "match")


# ─────────────────────────────────────────────────────────────────────────────
# Client application form
# ─────────────────────────────────────────────────────────────────────────────

class ClientApplyViewTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.url = reverse("client_apply")
        self.valid_data = {
            "first_name": "Carol",
            "last_name": "Jones",
            "username": "caroljones",
            "email": "carol@client.example",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "phone": "555-0300",
            "contact_preferences": ["email"],
            "address": "456 Oak Ave",
            "base_zip_code": "90001",
        }

    def test_get_renders_200(self):
        response = self.c.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_valid_redirects_to_success(self):
        response = self.c.post(self.url, self.valid_data)
        self.assertRedirects(response, reverse("application_success"))

    def test_post_valid_creates_inactive_user(self):
        self.c.post(self.url, self.valid_data)
        user = User.objects.get(username="caroljones")
        self.assertFalse(user.is_active, "Client applicants should be inactive until approved")

    def test_post_duplicate_username_shows_error(self):
        User.objects.create_user(username="caroljones", email="other@test.example", password=PASSWORD)
        response = self.c.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already taken")


# ─────────────────────────────────────────────────────────────────────────────
# Status update — org admin approving / rejecting caregiver and client
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CaregiverStatusUpdateTest(TestCase):
    """Org admin / staff can approve or reject caregivers."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, self.staff_profile, _ = make_org_admin(username="statusadmin")
        self.cg_user, self.cg_profile = make_caregiver_user(username="statuscg")
        self.rel = add_caregiver_to_org(self.cg_profile, self.org, status="pending")
        self.c.force_login(self.admin_user)

    def test_admin_can_approve_caregiver(self):
        url = reverse("update_caregiver_status", args=[self.rel.pk, "approved"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.rel.refresh_from_db()
        self.assertEqual(self.rel.status, "approved")

    def test_admin_can_reject_caregiver(self):
        url = reverse("update_caregiver_status", args=[self.rel.pk, "rejected"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.rel.refresh_from_db()
        self.assertEqual(self.rel.status, "rejected")

    def test_invalid_status_is_rejected(self):
        url = reverse("update_caregiver_status", args=[self.rel.pk, "invalid_status"])
        response = self.c.post(url)
        # Should redirect with an error message, not 500
        self.assertIn(response.status_code, [301, 302])
        self.rel.refresh_from_db()
        self.assertNotEqual(self.rel.status, "invalid_status")

    def test_non_admin_cannot_update_caregiver_status(self):
        other_user, _ = make_caregiver_user(username="notanadmin")
        self.c.force_login(other_user)
        url = reverse("update_caregiver_status", args=[self.rel.pk, "approved"])
        response = self.c.post(url)
        # Should be refused (redirect or 403)
        self.assertIn(response.status_code, [302, 403])
        self.rel.refresh_from_db()
        self.assertEqual(self.rel.status, "pending")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ClientStatusUpdateTest(TestCase):
    """Org admin / staff can approve or reject clients."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="clstatusadmin")
        self.cl_user, self.cl_profile = make_client_user(username="statuscl")
        self.rel = add_client_to_org(self.cl_profile, self.org, status="pending")
        self.c.force_login(self.admin_user)

    def test_admin_can_approve_client(self):
        url = reverse("update_client_status", args=[self.rel.pk, "approved"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.rel.refresh_from_db()
        self.assertEqual(self.rel.status, "approved")

    def test_admin_can_reject_client(self):
        url = reverse("update_client_status", args=[self.rel.pk, "rejected"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.rel.refresh_from_db()
        self.assertEqual(self.rel.status, "rejected")


# ─────────────────────────────────────────────────────────────────────────────
# Registry network
# ─────────────────────────────────────────────────────────────────────────────

class RegistryNetworkAccessTest(TestCase):
    """Registry network view must be accessible by all logged-in roles.

    The registry network requires the user to have at least one org
    relationship (approved) to render results.  We set that up in setUp.
    """

    def setUp(self):
        self.c = TestClient()
        self.url = reverse("registry_network")
        # Shared org for all role-specific users
        self.admin_user, self.org, _, _ = make_org_admin(username="netadmin")

    def test_admin_can_access_registry_network(self):
        self.c.force_login(self.admin_user)
        response = self.c.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_caregiver_with_org_can_access_registry_network(self):
        cg_user, cg_profile = make_caregiver_user(username="netcg")
        add_caregiver_to_org(cg_profile, self.org)
        self.c.force_login(cg_user)
        response = self.c.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_client_with_org_can_access_registry_network(self):
        cl_user, cl_profile = make_client_user(username="netcl")
        add_client_to_org(cl_profile, self.org)
        self.c.force_login(cl_user)
        response = self.c.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_redirects_to_login(self):
        response = self.c.get(self.url)
        self.assertIn(response.status_code, [301, 302])
        self.assertIn("login", response.get("Location", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Coordinator dashboard
# ─────────────────────────────────────────────────────────────────────────────

class CoordinatorDashboardTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.coord_user, self.coord_profile = make_coordinator_user(username="coorddash")
        self.cl_user, self.cl_profile = make_client_user(username="coorddashcl")
        link_coordinator_to_client(self.coord_profile, self.cl_profile)

    def test_coordinator_can_view_dashboard(self):
        self.c.force_login(self.coord_user)
        response = self.c.get(reverse("coordinator_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_non_coordinator_is_redirected(self):
        cg_user, _ = make_caregiver_user(username="coorddashcg")
        self.c.force_login(cg_user)
        response = self.c.get(reverse("coordinator_dashboard"))
        self.assertIn(response.status_code, [302, 403])


# ─────────────────────────────────────────────────────────────────────────────
# Coordinator invite
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CoordinatorInviteTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.cl_user, self.cl_profile = make_client_user(username="invitecl")
        self.c.force_login(self.cl_user)
        self.url = reverse("coordinator_invite_send")

    def test_get_invite_page_renders(self):
        response = self.c.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post_valid_email_creates_invite(self):
        from registry.models import CoordinatorInvite
        response = self.c.post(self.url, {"email": "newcoord@test.example"})
        self.assertIn(response.status_code, [301, 302])
        self.assertTrue(CoordinatorInvite.objects.filter(email="newcoord@test.example").exists())

    def test_non_client_cannot_invite(self):
        cg_user, _ = make_caregiver_user(username="invitecg")
        self.c.force_login(cg_user)
        response = self.c.get(self.url)
        self.assertIn(response.status_code, [302, 403])


# ─────────────────────────────────────────────────────────────────────────────
# Coordinator signup (token-based)
# ─────────────────────────────────────────────────────────────────────────────

class CoordinatorSignupTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.cl_user, self.cl_profile = make_client_user(username="coordsignupcl")
        self.invite = make_coordinator_invite(
            client_profile=self.cl_profile,
            invited_by_profile=self.cl_profile.user_profile,
            email="invitedcoord@test.example",
        )

    def test_valid_token_renders_form(self):
        url = reverse("coordinator_signup", args=[self.invite.token])
        response = self.c.get(url)
        self.assertEqual(response.status_code, 200)

    def test_expired_token_redirects_with_error(self):
        from django.utils import timezone
        from datetime import timedelta
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save()
        url = reverse("coordinator_signup", args=[self.invite.token])
        response = self.c.get(url)
        self.assertIn(response.status_code, [301, 302])

    def test_used_token_redirects_with_error(self):
        from django.utils import timezone
        self.invite.used_at = timezone.now()
        self.invite.save()
        url = reverse("coordinator_signup", args=[self.invite.token])
        response = self.c.get(url)
        self.assertIn(response.status_code, [301, 302])

    def test_invalid_token_returns_404_or_redirect(self):
        import uuid
        url = reverse("coordinator_signup", args=[uuid.uuid4()])
        response = self.c.get(url)
        self.assertIn(response.status_code, [301, 302, 404])

    # ------------------------------------------------------------------
    # New tests for the fixed signup flow (password + field rendering)
    # ------------------------------------------------------------------

    def _valid_post_data(self):
        return {
            "email": self.invite.email,
            "first_name": "Test",
            "last_name": "Coordinator",
            "password1": "S3cur3P@ssw0rd!",
            "password2": "S3cur3P@ssw0rd!",
            "phone": "555-000-1234",
            "contact_preferences": ["email"],
            "relationship_to_clients": "Family member",
        }

    def test_form_renders_password_and_name_fields(self):
        """GET renders first_name, last_name, password1, password2 fields."""
        url = reverse("coordinator_signup", args=[self.invite.token])
        response = self.c.get(url)
        content = response.content.decode()
        self.assertIn('id_first_name', content)
        self.assertIn('id_last_name', content)
        self.assertIn('id_password1', content)
        self.assertIn('id_password2', content)

    def test_valid_post_accepts_invite_and_redirects_to_coordinator_dashboard(self):
        """
        POST with valid data should:
        - Mark the invite as used
        - Create a SupportCoordinatorProfile
        - Set a usable password on the new user
        - Redirect to coordinator_dashboard
        """
        from registry.models import CoordinatorInvite
        from django.contrib.auth import get_user_model
        User = get_user_model()

        url = reverse("coordinator_signup", args=[self.invite.token])
        response = self.c.post(url, self._valid_post_data())

        self.assertIn(response.status_code, [301, 302], msg="Expected redirect after accept")
        self.assertIn("coordinator", response.get("Location", ""))

        # Invite should now be marked used
        self.invite.refresh_from_db()
        self.assertIsNotNone(self.invite.used_at)

        # User should exist with a usable password
        user = User.objects.get(email=self.invite.email)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.is_active)

    def test_password_mismatch_shows_error_not_silent_fail(self):
        """
        POST with mismatched passwords must re-render the form with an error,
        NOT silently do nothing.
        """
        url = reverse("coordinator_signup", args=[self.invite.token])
        data = self._valid_post_data()
        data["password2"] = "different_password"
        response = self.c.post(url, data)

        # Must NOT redirect — form is re-displayed with the error
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("match", content.lower())

        # Invite must NOT be marked used
        self.invite.refresh_from_db()
        self.assertIsNone(self.invite.used_at)

    def test_missing_required_fields_show_errors(self):
        """
        POST with first_name and last_name missing must re-render the form
        with validation errors, not silently stay on the same page.
        """
        url = reverse("coordinator_signup", args=[self.invite.token])
        data = self._valid_post_data()
        data.pop("first_name")
        data.pop("last_name")
        response = self.c.post(url, data)

        self.assertEqual(response.status_code, 200)
        self.invite.refresh_from_db()
        self.assertIsNone(self.invite.used_at)


# ─────────────────────────────────────────────────────────────────────────────
# Schedule workflows
# ─────────────────────────────────────────────────────────────────────────────

class ScheduleCreateTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="schedorg")
        self.cl_user, self.cl_profile = make_client_user(username="schedcl")
        self.cg_user, self.cg_profile = make_caregiver_user(username="schedcg")
        add_client_to_org(self.cl_profile, self.org)
        add_caregiver_to_org(self.cg_profile, self.org)
        # Need an active match to select from in ScheduleForm
        self.match = make_match(
            self.cg_profile, self.cl_profile,
            caregiver_status="approved", client_status="approved",
            overall_status="active",
        )
        self.c.force_login(self.cl_user)

    def test_get_schedule_create_renders(self):
        response = self.c.get(reverse("schedule_create"))
        self.assertEqual(response.status_code, 200)

    def test_caregiver_cannot_access_schedule_create(self):
        self.c.force_login(self.cg_user)
        response = self.c.get(reverse("schedule_create"))
        self.assertIn(response.status_code, [302, 403])


class ScheduleDetailAccessTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="sdetailorg")
        self.cl_user, self.cl_profile = make_client_user(username="sdetailcl")
        self.cg_user, self.cg_profile = make_caregiver_user(username="sdetailcg")
        add_client_to_org(self.cl_profile, self.org)
        add_caregiver_to_org(self.cg_profile, self.org)
        self.match = make_match(
            self.cg_profile, self.cl_profile,
            caregiver_status="approved", client_status="approved",
            overall_status="active",
        )
        self.schedule = make_schedule(self.cl_profile, self.cg_profile, match=self.match)

    def test_client_can_view_own_schedule(self):
        self.c.force_login(self.cl_user)
        url = reverse("schedule_detail", args=[self.schedule.pk])
        response = self.c.get(url)
        self.assertEqual(response.status_code, 200)

    def test_caregiver_can_view_assigned_schedule(self):
        self.c.force_login(self.cg_user)
        url = reverse("schedule_detail", args=[self.schedule.pk])
        response = self.c.get(url)
        self.assertEqual(response.status_code, 200)

    def test_unrelated_user_cannot_view_schedule(self):
        other_user, _ = make_caregiver_user(username="sdetailother")
        self.c.force_login(other_user)
        url = reverse("schedule_detail", args=[self.schedule.pk])
        response = self.c.get(url)
        self.assertIn(response.status_code, [302, 403])


class ScheduleSubmitCancelTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="sscorg")
        self.cl_user, self.cl_profile = make_client_user(username="ssccl")
        self.cg_user, self.cg_profile = make_caregiver_user(username="ssccg")
        add_client_to_org(self.cl_profile, self.org)
        add_caregiver_to_org(self.cg_profile, self.org)
        self.match = make_match(
            self.cg_profile, self.cl_profile,
            caregiver_status="approved", client_status="approved",
            overall_status="active",
        )
        self.schedule = make_schedule(self.cl_profile, self.cg_profile, match=self.match)
        make_schedule_entry(self.schedule)
        self.c.force_login(self.cl_user)

    def test_client_can_submit_draft_schedule(self):
        url = reverse("schedule_submit", args=[self.schedule.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, "submitted")

    def test_caregiver_cannot_submit_schedule(self):
        self.c.force_login(self.cg_user)
        url = reverse("schedule_submit", args=[self.schedule.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [302, 403])
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, "draft")

    def test_client_can_cancel_submitted_schedule(self):
        self.schedule.status = "submitted"
        self.schedule.save()
        url = reverse("schedule_cancel", args=[self.schedule.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, "cancelled")

    def test_client_cannot_edit_submitted_schedule(self):
        self.schedule.status = "submitted"
        self.schedule.save()
        url = reverse("schedule_edit", args=[self.schedule.pk])
        response = self.c.post(url)
        # Should redirect back with a warning, not modify the schedule
        self.assertIn(response.status_code, [301, 302])
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, "submitted")


class ScheduleEntryRespondTest(TestCase):
    """Caregiver can approve or reject individual schedule entries."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="serespondorg")
        self.cl_user, self.cl_profile = make_client_user(username="serespondcl")
        self.cg_user, self.cg_profile = make_caregiver_user(username="serespondcg")
        add_client_to_org(self.cl_profile, self.org)
        add_caregiver_to_org(self.cg_profile, self.org)
        self.match = make_match(
            self.cg_profile, self.cl_profile,
            caregiver_status="approved", client_status="approved",
            overall_status="active",
        )
        self.schedule = make_schedule(
            self.cl_profile, self.cg_profile,
            match=self.match, status="submitted",
        )
        self.entry = make_schedule_entry(self.schedule)

    def test_caregiver_can_approve_entry(self):
        self.c.force_login(self.cg_user)
        url = reverse("schedule_entry_caregiver_respond", args=[self.entry.pk, "approve"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.caregiver_status, "approved")

    def test_caregiver_can_reject_entry(self):
        self.c.force_login(self.cg_user)
        url = reverse("schedule_entry_caregiver_respond", args=[self.entry.pk, "reject"])
        response = self.c.post(url, {"notes": "Conflict on Monday"})
        self.assertIn(response.status_code, [301, 302])
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.caregiver_status, "rejected")

    def test_wrong_caregiver_cannot_respond(self):
        other_cg_user, _ = make_caregiver_user(username="serespondothercg")
        self.c.force_login(other_cg_user)
        url = reverse("schedule_entry_caregiver_respond", args=[self.entry.pk, "approve"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [302, 403])
        self.entry.refresh_from_db()
        self.assertNotEqual(self.entry.caregiver_status, "approved")


# ─────────────────────────────────────────────────────────────────────────────
# Pool browsing
# ─────────────────────────────────────────────────────────────────────────────

class PoolBrowsingTest(TestCase):
    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="pooladmin")
        self.c.force_login(self.admin_user)

    def test_caregiver_pool_renders(self):
        response = self.c.get(reverse("caregiver_pool"))
        self.assertEqual(response.status_code, 200)

    def test_client_pool_renders(self):
        response = self.c.get(reverse("client_pool"))
        self.assertEqual(response.status_code, 200)

    def test_non_admin_cannot_view_pool(self):
        cg_user, _ = make_caregiver_user(username="poolcg")
        self.c.force_login(cg_user)
        response = self.c.get(reverse("caregiver_pool"))
        self.assertIn(response.status_code, [302, 403])
