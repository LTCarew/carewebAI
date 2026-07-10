"""
matching/tests_views.py — Django TestCase view tests for the matching module.

Covers:
  - Caregiver-initiated match request (POST)
  - Client-initiated match request (POST)
  - Staff-created match proposal (POST)
  - Match approve/decline by caregiver
  - Match approve/decline by client
  - Wrong-party permission denial
  - Staff cannot approve/decline (PermissionError path)
  - Match cancellation by authorized / unauthorized actor
  - AI redirect endpoints
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from django.test import TestCase, Client as TestClient, override_settings
from django.urls import reverse

from tests_helpers import (
    make_org_admin, make_staff_user,
    make_caregiver_user, add_caregiver_to_org,
    make_client_user, add_client_to_org,
    make_match,
)
from matching.models import Match

# All matching view tests use local scoring only (no OpenAI)
OPENAI_OFF = override_settings(OPENAI_MATCH_ENABLED=False, OPENAI_API_KEY="")


# ─────────────────────────────────────────────────────────────────────────────
# Caregiver-initiated match request
# ─────────────────────────────────────────────────────────────────────────────

@OPENAI_OFF
class CaregiverRequestMatchTest(TestCase):
    """POST /match/request/caregiver/<client_id>/ — caregiver initiates a match."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="cgreqadmin")
        self.cg_user, self.cg_profile = make_caregiver_user(username="cgreqcg")
        self.cl_user, self.cl_profile = make_client_user(username="cgreqcl")
        add_caregiver_to_org(self.cg_profile, self.org)
        add_client_to_org(self.cl_profile, self.org)

    def test_caregiver_can_request_match(self):
        self.c.force_login(self.cg_user)
        url = reverse("caregiver_request_match", args=[self.cl_profile.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.assertTrue(
            Match.objects.filter(
                caregiver=self.cg_profile,
                client=self.cl_profile,
                initiated_by="caregiver",
            ).exists()
        )

    def test_match_starts_with_pending_client_status(self):
        self.c.force_login(self.cg_user)
        url = reverse("caregiver_request_match", args=[self.cl_profile.pk])
        self.c.post(url)
        match = Match.objects.get(caregiver=self.cg_profile, client=self.cl_profile)
        self.assertEqual(match.caregiver_status, "approved")
        self.assertEqual(match.client_status, "pending")
        self.assertEqual(match.status, "pending")

    def test_client_cannot_use_caregiver_request_endpoint(self):
        self.c.force_login(self.cl_user)
        url = reverse("caregiver_request_match", args=[self.cl_profile.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [302, 403])
        self.assertFalse(Match.objects.filter(caregiver=self.cg_profile).exists())

    def test_duplicate_match_request_does_not_create_second_match(self):
        """A duplicate active match should not create a second record."""
        make_match(
            self.cg_profile, self.cl_profile,
            caregiver_status="approved", client_status="pending",
        )
        self.c.force_login(self.cg_user)
        url = reverse("caregiver_request_match", args=[self.cl_profile.pk])
        self.c.post(url)
        self.assertEqual(
            Match.objects.filter(caregiver=self.cg_profile, client=self.cl_profile).count(),
            1
        )


# ─────────────────────────────────────────────────────────────────────────────
# Client-initiated match request
# ─────────────────────────────────────────────────────────────────────────────

@OPENAI_OFF
class ClientRequestMatchTest(TestCase):
    """POST /match/request/client/<caregiver_id>/ — client initiates a match."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="clreqadmin")
        self.cg_user, self.cg_profile = make_caregiver_user(username="clreqcg")
        self.cl_user, self.cl_profile = make_client_user(username="clreqcl")
        add_caregiver_to_org(self.cg_profile, self.org)
        add_client_to_org(self.cl_profile, self.org)

    def test_client_can_request_match(self):
        self.c.force_login(self.cl_user)
        url = reverse("client_request_match", args=[self.cg_profile.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.assertTrue(
            Match.objects.filter(
                caregiver=self.cg_profile,
                client=self.cl_profile,
                initiated_by="client",
            ).exists()
        )

    def test_match_starts_with_pending_caregiver_status(self):
        self.c.force_login(self.cl_user)
        url = reverse("client_request_match", args=[self.cg_profile.pk])
        self.c.post(url)
        match = Match.objects.get(caregiver=self.cg_profile, client=self.cl_profile)
        self.assertEqual(match.caregiver_status, "pending")
        self.assertEqual(match.client_status, "approved")
        self.assertEqual(match.status, "pending")

    def test_caregiver_cannot_use_client_request_endpoint(self):
        self.c.force_login(self.cg_user)
        url = reverse("client_request_match", args=[self.cg_profile.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [302, 403])


# ─────────────────────────────────────────────────────────────────────────────
# Staff-created match proposal
# ─────────────────────────────────────────────────────────────────────────────

@OPENAI_OFF
class StaffCreateMatchTest(TestCase):
    """POST /match/create/staff/ — staff proposes a match."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="staffmatchadmin")
        self.cg_user, self.cg_profile = make_caregiver_user(username="staffmatchcg")
        self.cl_user, self.cl_profile = make_client_user(username="staffmatchcl")
        add_caregiver_to_org(self.cg_profile, self.org)
        add_client_to_org(self.cl_profile, self.org)
        self.c.force_login(self.admin_user)

    def test_staff_can_create_match(self):
        url = reverse("staff_create_match")
        response = self.c.post(url, {
            "caregiver_id": self.cg_profile.pk,
            "client_id": self.cl_profile.pk,
            "notes": "Staff proposed this match",
        })
        self.assertIn(response.status_code, [301, 302])
        self.assertTrue(
            Match.objects.filter(
                caregiver=self.cg_profile,
                client=self.cl_profile,
                initiated_by="staff",
            ).exists()
        )

    def test_match_starts_with_both_pending(self):
        url = reverse("staff_create_match")
        self.c.post(url, {
            "caregiver_id": self.cg_profile.pk,
            "client_id": self.cl_profile.pk,
        })
        match = Match.objects.get(caregiver=self.cg_profile, client=self.cl_profile)
        self.assertEqual(match.caregiver_status, "pending")
        self.assertEqual(match.client_status, "pending")
        self.assertEqual(match.status, "pending")

    def test_non_staff_cannot_use_staff_create_endpoint(self):
        self.c.force_login(self.cg_user)
        url = reverse("staff_create_match")
        response = self.c.post(url, {
            "caregiver_id": self.cg_profile.pk,
            "client_id": self.cl_profile.pk,
        })
        self.assertIn(response.status_code, [302, 403])
        self.assertFalse(Match.objects.filter(caregiver=self.cg_profile).exists())


# ─────────────────────────────────────────────────────────────────────────────
# Match respond — caregiver approve / decline
# ─────────────────────────────────────────────────────────────────────────────

class MatchRespondCaregiverTest(TestCase):
    """POST /match/<id>/<action>/ from caregiver perspective."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="respondcgadmin")
        self.cg_user, self.cg_profile = make_caregiver_user(username="respondcg")
        self.cl_user, self.cl_profile = make_client_user(username="respondcgcl")
        add_caregiver_to_org(self.cg_profile, self.org)
        add_client_to_org(self.cl_profile, self.org)
        # Staff-initiated so caregiver has pending status
        self.match = make_match(
            self.cg_profile, self.cl_profile,
            initiated_by="staff",
            caregiver_status="pending",
            client_status="pending",
            overall_status="pending",
        )

    def test_caregiver_can_approve_match(self):
        self.c.force_login(self.cg_user)
        url = reverse("match_respond", args=[self.match.pk, "approve"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.match.refresh_from_db()
        self.assertEqual(self.match.caregiver_status, "approved")

    def test_caregiver_can_decline_match(self):
        self.c.force_login(self.cg_user)
        url = reverse("match_respond", args=[self.match.pk, "decline"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.match.refresh_from_db()
        self.assertEqual(self.match.caregiver_status, "declined")

    def test_wrong_caregiver_cannot_approve(self):
        other_cg_user, _ = make_caregiver_user(username="wrongcg")
        self.c.force_login(other_cg_user)
        url = reverse("match_respond", args=[self.match.pk, "approve"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.match.refresh_from_db()
        # Status must remain unchanged
        self.assertEqual(self.match.caregiver_status, "pending")

    def test_match_becomes_active_after_both_approve(self):
        # Client-initiated so caregiver has pending status
        match2 = make_match(
            self.cg_profile, self.cl_profile,
            initiated_by="client",
            caregiver_status="pending",
            client_status="approved",
            overall_status="pending",
        )
        self.c.force_login(self.cg_user)
        url = reverse("match_respond", args=[match2.pk, "approve"])
        self.c.post(url)
        match2.refresh_from_db()
        self.assertEqual(match2.status, "active")


# ─────────────────────────────────────────────────────────────────────────────
# Match respond — client approve / decline
# ─────────────────────────────────────────────────────────────────────────────

class MatchRespondClientTest(TestCase):
    """POST /match/<id>/<action>/ from client perspective."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="respondcladmin")
        self.cg_user, self.cg_profile = make_caregiver_user(username="respondclcg")
        self.cl_user, self.cl_profile = make_client_user(username="respondcl")
        add_caregiver_to_org(self.cg_profile, self.org)
        add_client_to_org(self.cl_profile, self.org)
        # Caregiver-initiated so client has pending status
        self.match = make_match(
            self.cg_profile, self.cl_profile,
            initiated_by="caregiver",
            caregiver_status="approved",
            client_status="pending",
            overall_status="pending",
        )

    def test_client_can_approve_match(self):
        self.c.force_login(self.cl_user)
        url = reverse("match_respond", args=[self.match.pk, "approve"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.match.refresh_from_db()
        self.assertEqual(self.match.client_status, "approved")
        self.assertEqual(self.match.status, "active")

    def test_client_can_decline_match(self):
        self.c.force_login(self.cl_user)
        url = reverse("match_respond", args=[self.match.pk, "decline"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.match.refresh_from_db()
        self.assertEqual(self.match.client_status, "declined")

    def test_wrong_client_cannot_approve(self):
        other_cl_user, _ = make_client_user(username="wrongcl")
        self.c.force_login(other_cl_user)
        url = reverse("match_respond", args=[self.match.pk, "approve"])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        self.match.refresh_from_db()
        self.assertEqual(self.match.client_status, "pending")


# ─────────────────────────────────────────────────────────────────────────────
# Staff cannot approve/decline via match_respond
# ─────────────────────────────────────────────────────────────────────────────

class StaffMatchRespondDeniedTest(TestCase):
    """Staff cannot use match_respond to approve/decline (PermissionError path)."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="staffrespondadmin")
        self.cg_user, self.cg_profile = make_caregiver_user(username="staffrespondcg")
        self.cl_user, self.cl_profile = make_client_user(username="staffrespondcl")
        add_caregiver_to_org(self.cg_profile, self.org)
        add_client_to_org(self.cl_profile, self.org)
        self.match = make_match(
            self.cg_profile, self.cl_profile,
            initiated_by="staff",
            caregiver_status="pending",
            client_status="pending",
            overall_status="pending",
        )

    def test_staff_approve_redirects_with_error_not_500(self):
        """Staff calling approve/decline must not crash with 500."""
        self.c.force_login(self.admin_user)
        url = reverse("match_respond", args=[self.match.pk, "approve"])
        response = self.c.post(url)
        # Must redirect (with error message) — never 500
        self.assertNotEqual(response.status_code, 500)
        self.assertIn(response.status_code, [301, 302])
        # Match statuses must remain unchanged
        self.match.refresh_from_db()
        self.assertEqual(self.match.caregiver_status, "pending")
        self.assertEqual(self.match.client_status, "pending")


# ─────────────────────────────────────────────────────────────────────────────
# Match cancellation
# ─────────────────────────────────────────────────────────────────────────────

class MatchCancelTest(TestCase):
    """POST /match/<id>/cancel/ — authorized actor can cancel, unauthorized cannot.

    NOTE: The match_cancel view's permission check calls
    get_active_organization(request) which uses the session to find the user's
    org.  In tests we must pre-seed `active_organization_id` in the session
    after force_login so the view can locate the correct org and resolve the
    user's role before the permission gate is evaluated.
    """

    def setUp(self):
        self.c = TestClient()
        self.admin_user, self.org, _, _ = make_org_admin(username="canceladmin")
        self.cg_user, self.cg_profile = make_caregiver_user(username="cancelcg")
        self.cl_user, self.cl_profile = make_client_user(username="cancelcl")
        add_caregiver_to_org(self.cg_profile, self.org)
        add_client_to_org(self.cl_profile, self.org)

    def _make_pending_match(self):
        return make_match(
            self.cg_profile, self.cl_profile,
            initiated_by="caregiver",
            caregiver_status="approved",
            client_status="pending",
            overall_status="pending",
        )

    def _seed_session_org(self, user):
        """Log user in and pre-set the active org in their session."""
        self.c.force_login(user)
        session = self.c.session
        session['active_organization_id'] = self.org.pk
        session.save()

    def test_caregiver_can_cancel_pending_match(self):
        match = self._make_pending_match()
        self._seed_session_org(self.cg_user)
        url = reverse("match_cancel", args=[match.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        match.refresh_from_db()
        self.assertEqual(match.status, "cancelled")

    def test_client_can_cancel_pending_match(self):
        match = self._make_pending_match()
        self._seed_session_org(self.cl_user)
        url = reverse("match_cancel", args=[match.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        match.refresh_from_db()
        self.assertEqual(match.status, "cancelled")

    def test_unrelated_user_cannot_cancel(self):
        match = self._make_pending_match()
        other_user, _ = make_caregiver_user(username="cancelother")
        self.c.force_login(other_user)
        url = reverse("match_cancel", args=[match.pk])
        response = self.c.post(url)
        self.assertIn(response.status_code, [301, 302])
        match.refresh_from_db()
        self.assertNotEqual(match.status, "cancelled")

    def test_cannot_cancel_already_cancelled_match(self):
        match = self._make_pending_match()
        match.status = "cancelled"
        match.save()
        self._seed_session_org(self.cg_user)
        url = reverse("match_cancel", args=[match.pk])
        response = self.c.post(url)
        # Must not crash — redirect or error page expected
        self.assertNotEqual(response.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# AI redirect endpoints
# ─────────────────────────────────────────────────────────────────────────────

class AIMatchRedirectTest(TestCase):
    """The /match/ai/* endpoints redirect authenticated users to /registry/network/."""

    def setUp(self):
        self.c = TestClient()
        self.admin_user, _, _, _ = make_org_admin(username="airedir")
        self.c.force_login(self.admin_user)

    def test_ai_match_caregiver_redirects(self):
        response = self.c.get(reverse("ai_match_caregiver"))
        self.assertIn(response.status_code, [301, 302])
        location = response.get("Location", "")
        self.assertIn("network", location)

    def test_ai_match_client_redirects(self):
        response = self.c.get(reverse("ai_match_client"))
        self.assertIn(response.status_code, [301, 302])
        location = response.get("Location", "")
        self.assertIn("network", location)

    def test_ai_match_staff_redirects(self):
        response = self.c.get(reverse("ai_match_staff"))
        self.assertIn(response.status_code, [301, 302])
        location = response.get("Location", "")
        self.assertIn("network", location)

    def test_unauthenticated_ai_redirects_to_login(self):
        self.c.logout()
        response = self.c.get(reverse("ai_match_caregiver"))
        self.assertIn(response.status_code, [301, 302])
        self.assertIn("login", response.get("Location", ""))
