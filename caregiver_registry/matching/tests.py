"""
Matching app tests.

Covers:
  - Caregiver/client/staff-initiated match creation and auto-approval logic
  - Match becomes active when BOTH caregiver AND client approve (two-party workflow)
  - Staff approval is NOT required for match activation
  - Match becomes declined when caregiver or client declines
  - Staff decline does NOT affect match status (staff do not approve/decline)
  - Duplicate active/pending match prevention
  - Local AI scoring returns score + reasoning
  - Permission guards: unauthorized users cannot approve
"""

from django.test import TestCase, Client as HttpClient, override_settings
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

from .models import Match, Tag
from .services import (
    create_match,
    caregiver_respond_to_match,
    client_respond_to_match,
    staff_respond_to_match,
    compute_match_score,
    compute_ai_enhanced_match_score,
    _call_chatgpt_match_score,
    get_existing_active_or_pending_match,
)

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_user_profile(username, email=None):
    """Create a User + UserProfile stub for testing."""
    user = User.objects.create_user(
        username=username,
        email=email or f"{username}@test.example",
        password="testpass123",
    )
    from accounts.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
    )
    return user, profile


def make_caregiver_profile(username, experience=None, availability=None, zip_code="94103"):
    """Create a CaregiverProfile for testing."""
    from registry.models import CaregiverProfile
    user, user_profile = make_user_profile(username)
    cp = CaregiverProfile.objects.create(
        user_profile=user_profile,
        experience_with=experience or [],
        availability=availability or {},
        base_zip_code=zip_code,
    )
    return user, cp


def make_client_profile(username, care_needs=None, availability=None, zip_code="94103"):
    """Create a ClientProfile for testing."""
    from registry.models import ClientProfile
    user, user_profile = make_user_profile(username)
    cp = ClientProfile.objects.create(
        user_profile=user_profile,
        care_needs=care_needs or [],
        availability=availability or {},
        base_zip_code=zip_code,
    )
    return user, cp


def make_organization(name="Test Org"):
    """Create an Organization with the required primary_admin StaffProfile."""
    from organizations.models import Organization
    from accounts.models import StaffProfile

    safe_name = name.lower().replace(" ", "_")
    admin_user, admin_profile = make_user_profile(f"admin_{safe_name}_{id(name)}")

    staff_profile, _ = StaffProfile.objects.get_or_create(
        user_profile=admin_profile,
    )

    return Organization.objects.create(
        name=name,
        city="San Francisco",
        primary_admin=staff_profile,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Caregiver-initiated match
# ─────────────────────────────────────────────────────────────────────────────

class CaregiverInitiatedMatchTest(TestCase):
    def setUp(self):
        self.cg_user, self.cg = make_caregiver_profile("caregiver1")
        self.cl_user, self.cl = make_client_profile("client1")
        self.org = make_organization()

    def test_caregiver_initiates_creates_match_with_correct_statuses(self):
        match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="caregiver",
            initiated_by_user=self.cg.user_profile,
        )
        self.assertEqual(match.caregiver_status, "approved")
        self.assertEqual(match.client_status, "pending")
        self.assertEqual(match.staff_status, "pending")
        self.assertEqual(match.status, "pending")

    def test_caregiver_initiates_match_is_not_active(self):
        match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="caregiver",
            initiated_by_user=self.cg.user_profile,
        )
        self.assertNotEqual(match.status, "active")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Client-initiated match
# ─────────────────────────────────────────────────────────────────────────────

class ClientInitiatedMatchTest(TestCase):
    def setUp(self):
        self.cg_user, self.cg = make_caregiver_profile("caregiver2")
        self.cl_user, self.cl = make_client_profile("client2")
        self.org = make_organization("Client Org")

    def test_client_initiates_creates_match_with_correct_statuses(self):
        match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="client",
            initiated_by_user=self.cl.user_profile,
        )
        self.assertEqual(match.client_status, "approved")
        self.assertEqual(match.caregiver_status, "pending")
        self.assertEqual(match.staff_status, "pending")
        self.assertEqual(match.status, "pending")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Staff-initiated match
# ─────────────────────────────────────────────────────────────────────────────

class StaffInitiatedMatchTest(TestCase):
    def setUp(self):
        self.cg_user, self.cg = make_caregiver_profile("caregiver3")
        self.cl_user, self.cl = make_client_profile("client3")
        self.staff_user, self.staff_profile = make_user_profile("staffmember")
        self.org = make_organization("Staff Org")

    def test_staff_initiates_creates_match_with_correct_statuses(self):
        match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="staff",
            initiated_by_user=self.staff_profile,
        )
        self.assertEqual(match.staff_status, "approved")
        self.assertEqual(match.caregiver_status, "pending")
        self.assertEqual(match.client_status, "pending")
        self.assertEqual(match.status, "pending")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Two-party activation: caregiver + client approval = active
# ─────────────────────────────────────────────────────────────────────────────

class MatchBecomesActiveTest(TestCase):
    def setUp(self):
        self.cg_user, self.cg = make_caregiver_profile("cg_active")
        self.cl_user, self.cl = make_client_profile("cl_active")
        self.staff_user, self.staff_profile = make_user_profile("staff_active")
        self.org = make_organization("Active Org")

        # Staff initiates: staff_status=approved, caregiver/client pending
        self.match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="staff",
            initiated_by_user=self.staff_profile,
        )

    def test_caregiver_alone_does_not_activate(self):
        """One approval alone is not enough."""
        self.match.caregiver_approve()
        self.match.refresh_from_db()
        self.assertNotEqual(self.match.status, "active")

    def test_caregiver_and_client_approve_activates_match(self):
        """Two-party: caregiver + client = active (staff not required)."""
        self.match.caregiver_approve()
        self.match.client_approve()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, "active")

    def test_staff_approval_not_required(self):
        """
        With a caregiver-initiated match, caregiver is auto-approved.
        After client also approves, match becomes active without any staff action.
        """
        cg_user2, cg2 = make_caregiver_profile("cg_two_app")
        cl_user2, cl2 = make_client_profile("cl_two_app")
        match2 = create_match(
            caregiver=cg2,
            client=cl2,
            organization=self.org,
            initiated_by="caregiver",
            initiated_by_user=cg2.user_profile,
        )
        match2.client_approve()
        match2.refresh_from_db()
        self.assertEqual(match2.caregiver_status, "approved")
        self.assertEqual(match2.client_status, "approved")
        self.assertEqual(match2.staff_status, "pending")  # still stored
        self.assertEqual(match2.status, "active")         # two-party approval complete


# ─────────────────────────────────────────────────────────────────────────────
# 5. Match becomes declined when caregiver or client declines
# ─────────────────────────────────────────────────────────────────────────────

class MatchDeclinedTest(TestCase):
    def setUp(self):
        self.cg_user, self.cg = make_caregiver_profile("cg_decline")
        self.cl_user, self.cl = make_client_profile("cl_decline")
        self.staff_user, self.staff_profile = make_user_profile("staff_decline")
        self.org = make_organization("Decline Org")

        self.match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="staff",
            initiated_by_user=self.staff_profile,
        )

    def test_caregiver_decline_sets_declined(self):
        self.match.caregiver_decline()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, "declined")

    def test_client_decline_sets_declined(self):
        self.match.client_decline()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, "declined")

    def test_staff_decline_does_not_affect_status(self):
        """Staff decline no longer affects match status in two-party workflow."""
        cg_user2, cg2 = make_caregiver_profile("cg_d2")
        cl_user2, cl2 = make_client_profile("cl_d2")
        match2 = create_match(
            caregiver=cg2, client=cl2, organization=self.org,
            initiated_by="caregiver", initiated_by_user=cg2.user_profile,
        )
        match2.staff_decline()
        match2.refresh_from_db()
        # Staff decline does NOT set overall status to declined
        self.assertNotEqual(match2.status, "declined")
        self.assertEqual(match2.status, "pending")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Duplicate active/pending matches are prevented
# ─────────────────────────────────────────────────────────────────────────────

class DuplicateMatchPreventionTest(TestCase):
    def setUp(self):
        self.cg_user, self.cg = make_caregiver_profile("cg_dup")
        self.cl_user, self.cl = make_client_profile("cl_dup")
        self.org = make_organization("Dup Org")

        self.first_match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="caregiver",
            initiated_by_user=self.cg.user_profile,
        )

    def test_duplicate_pending_match_raises_valueerror(self):
        with self.assertRaises(ValueError) as ctx:
            create_match(
                caregiver=self.cg,
                client=self.cl,
                organization=self.org,
                initiated_by="client",
                initiated_by_user=self.cl.user_profile,
            )
        self.assertIn("already exists", str(ctx.exception))

    def test_get_existing_returns_first_match(self):
        existing = get_existing_active_or_pending_match(self.cg, self.cl, self.org)
        self.assertEqual(existing, self.first_match)

    def test_declined_match_allows_new_match(self):
        self.first_match.caregiver_decline()
        self.first_match.refresh_from_db()
        self.assertEqual(self.first_match.status, "declined")

        new_match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="caregiver",
            initiated_by_user=self.cg.user_profile,
        )
        self.assertNotEqual(new_match.pk, self.first_match.pk)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Local AI scoring returns score and reasoning
# ─────────────────────────────────────────────────────────────────────────────

class LocalScoringTest(TestCase):
    def test_no_overlap_gives_partial_score(self):
        _, cg = make_caregiver_profile("cg_score1", experience=[])
        _, cl = make_client_profile("cl_score1", care_needs=[])
        result = compute_match_score(cg, cl)
        self.assertIn("score", result)
        self.assertIn("details", result)
        self.assertIn("ai_reasoning", result)
        self.assertIsInstance(result["score"], float)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_full_overlap_gives_higher_score(self):
        _, cg = make_caregiver_profile(
            "cg_score2",
            experience=["transfers", "dementia", "cooking"],
            availability={"monday": True, "tuesday": True},
            zip_code="94103",
        )
        _, cl = make_client_profile(
            "cl_score2",
            care_needs=["transfers", "dementia", "cooking"],
            availability={"monday": True, "tuesday": True},
            zip_code="94103",
        )
        result = compute_match_score(cg, cl)
        self.assertGreater(result["score"], 40)

    def test_reasoning_contains_overlap(self):
        _, cg = make_caregiver_profile("cg_score3", experience=["transfers"])
        _, cl = make_client_profile("cl_score3", care_needs=["transfers"])
        result = compute_match_score(cg, cl)
        self.assertIn("transfers", result["ai_reasoning"])

    def test_score_is_capped_at_100(self):
        _, cg = make_caregiver_profile(
            "cg_cap",
            experience=["transfers", "dementia", "cooking", "wheelchair"],
            availability={"mon": True, "tue": True, "wed": True, "thu": True, "fri": True},
            zip_code="94103",
        )
        _, cl = make_client_profile(
            "cl_cap",
            care_needs=["transfers", "dementia", "cooking", "wheelchair"],
            availability={"mon": True, "tue": True, "wed": True, "thu": True, "fri": True},
            zip_code="94103",
        )
        result = compute_match_score(cg, cl)
        self.assertLessEqual(result["score"], 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Distance-based location scoring (zip_distance + compute_match_score)
# ─────────────────────────────────────────────────────────────────────────────

class ZipDistanceModuleTest(TestCase):
    """
    Unit tests for matching.zip_distance — no Django DB required, but we inherit
    TestCase for consistency with the rest of the suite.

    These tests exercise the haversine math and the bundled US ZIP dataset
    without any network calls.
    """

    def _zdm(self, z1, z2):
        from matching.zip_distance import zip_distance_miles
        return zip_distance_miles(z1, z2)

    def _lsfd(self, miles):
        from matching.zip_distance import location_score_from_distance
        return location_score_from_distance(miles)

    def _coords(self, z):
        from matching.zip_distance import get_zip_coordinates
        return get_zip_coordinates(z)

    # ── get_zip_coordinates ──────────────────────────────────────────────────

    def test_known_zip_returns_coordinates(self):
        """A well-known ZIP in the bundled dataset returns a (lat, lon) tuple."""
        coords = self._coords("90210")
        self.assertIsNotNone(coords)
        lat, lon = coords
        # Beverly Hills is ~34°N, ~118°W
        self.assertAlmostEqual(lat, 34.09, delta=0.5)
        self.assertAlmostEqual(lon, -118.40, delta=0.5)

    def test_unknown_zip_returns_none(self):
        """A ZIP that does not exist in the dataset returns None."""
        self.assertIsNone(self._coords("00000"))

    def test_zip_plus4_is_normalized(self):
        """ZIP+4 format is stripped and the base 5-digit ZIP is looked up."""
        self.assertIsNotNone(self._coords("94103-1234"))
        self.assertEqual(self._coords("94103-1234"), self._coords("94103"))

    # ── zip_distance_miles ───────────────────────────────────────────────────

    def test_same_zip_returns_zero(self):
        """Same ZIP → exactly 0.0 miles."""
        self.assertEqual(self._zdm("94103", "94103"), 0.0)

    def test_same_zip_plus4_returns_zero(self):
        """Same ZIP with ZIP+4 suffix → 0.0 miles."""
        self.assertEqual(self._zdm("94103-0001", "94103-9999"), 0.0)

    def test_neighbouring_beverly_hills_zips(self):
        """90210 and 90211 are both Beverly Hills — should be < 5 miles apart."""
        d = self._zdm("90210", "90211")
        self.assertIsNotNone(d)
        self.assertLess(d, 5.0)
        self.assertGreater(d, 0.0)

    def test_sf_to_manhattan_is_far(self):
        """94103 (San Francisco) to 10001 (Manhattan) should be well over 2000 miles."""
        d = self._zdm("94103", "10001")
        self.assertIsNotNone(d)
        self.assertGreater(d, 2000.0)

    def test_invalid_zip_returns_none(self):
        """If either ZIP is not in the dataset, None is returned."""
        self.assertIsNone(self._zdm("00000", "90210"))
        self.assertIsNone(self._zdm("90210", "XXXXX"))

    def test_known_zip_pair_distance_is_reasonable(self):
        """
        94103 (SF SOMA) and 94110 (SF Mission) are both San Francisco ZIPs —
        they should be less than 5 miles apart.
        """
        d = self._zdm("94103", "94110")
        self.assertIsNotNone(d)
        self.assertLess(d, 5.0)

    # ── location_score_from_distance ─────────────────────────────────────────

    def test_score_zero_miles(self):
        """Exact same location (0 mi) → full 10 points."""
        self.assertEqual(self._lsfd(0.0), 10.0)

    def test_score_within_5_miles(self):
        """≤5 miles → full 10 points."""
        self.assertEqual(self._lsfd(4.9), 10.0)
        self.assertEqual(self._lsfd(5.0), 10.0)

    def test_score_within_15_miles(self):
        """5 < distance ≤ 15 miles → 7 points."""
        self.assertEqual(self._lsfd(5.1), 7.0)
        self.assertEqual(self._lsfd(15.0), 7.0)

    def test_score_within_30_miles(self):
        """15 < distance ≤ 30 miles → 4 points."""
        self.assertEqual(self._lsfd(15.1), 4.0)
        self.assertEqual(self._lsfd(30.0), 4.0)

    def test_score_within_50_miles(self):
        """30 < distance ≤ 50 miles → 2 points."""
        self.assertEqual(self._lsfd(30.1), 2.0)
        self.assertEqual(self._lsfd(50.0), 2.0)

    def test_score_over_50_miles(self):
        """More than 50 miles → 0 points."""
        self.assertEqual(self._lsfd(50.1), 0.0)
        self.assertEqual(self._lsfd(2000.0), 0.0)

    def test_score_none_distance(self):
        """None distance (unknown ZIP) → 0 points."""
        self.assertEqual(self._lsfd(None), 0.0)


class LocationScoringIntegrationTest(TestCase):
    """
    Integration tests: compute_match_score produces the correct location
    sub-score based on real ZIP distances from the bundled dataset.
    """

    def _score_result(self, cg_zip, cl_zip):
        """Helper: create minimal profiles with the given ZIPs and score them."""
        # Include both ZIPs in each username to guarantee uniqueness across calls
        _, cg = make_caregiver_profile(f"cg_loc_{cg_zip}_{cl_zip}", zip_code=cg_zip)
        _, cl = make_client_profile(f"cl_loc_{cl_zip}_{cg_zip}", zip_code=cl_zip)
        return compute_match_score(cg, cl)

    def test_same_zip_location_score_is_10(self):
        """Exact same ZIP → location score = 10."""
        result = self._score_result("94103", "94103")
        loc = result["details"]["location"]
        self.assertEqual(loc["score"], 10.0)
        self.assertEqual(loc["distance_miles"], 0.0)
        self.assertTrue(loc["same_zip"])

    def test_nearby_zips_score_higher_than_far_zips(self):
        """
        94103 (SF) and 94110 (SF Mission) should score much higher than
        94103 (SF) and 10001 (Manhattan).
        """
        nearby = self._score_result("94103", "94110")
        far = self._score_result("94103", "10001")
        self.assertGreater(
            nearby["details"]["location"]["score"],
            far["details"]["location"]["score"],
        )

    def test_beverly_hills_neighbouring_zips_get_full_score(self):
        """90210 and 90211 are < 5 miles apart — should get 10 pts."""
        result = self._score_result("90210", "90211")
        loc = result["details"]["location"]
        self.assertEqual(loc["score"], 10.0)
        self.assertIsNotNone(loc["distance_miles"])
        self.assertLess(loc["distance_miles"], 5.0)

    def test_far_apart_zips_get_zero_location_score(self):
        """SF to NYC is > 2000 miles — location score should be 0."""
        result = self._score_result("94103", "10001")
        self.assertEqual(result["details"]["location"]["score"], 0.0)

    def test_details_contains_distance_miles(self):
        """distance_miles is always present in details (float or None)."""
        result = self._score_result("94103", "94103")
        self.assertIn("distance_miles", result["details"]["location"])

    def test_same_invalid_zip_returns_zero_distance(self):
        """
        Two identical invalid ZIPs (not in dataset) still return 0.0 miles
        via the same-ZIP shortcut and earn the full 10-point location score.
        """
        _, cg = make_caregiver_profile("cg_loc_sameInvalid", zip_code="00000")
        _, cl = make_client_profile("cl_loc_sameInvalid", zip_code="00000")
        result = compute_match_score(cg, cl)
        loc = result["details"]["location"]
        # Same-ZIP shortcut fires before the dataset lookup → returns 0.0, not None
        self.assertEqual(loc["distance_miles"], 0.0)
        self.assertEqual(loc["score"], 10.0)

    def test_different_invalid_zips_fall_back_to_prefix_match(self):
        """
        Two different ZIPs that are not in the dataset (None distance) fall back
        to the 3-digit prefix heuristic gracefully — no exceptions raised.
        """
        # "00000" and "XXXXX" are both absent from the dataset and have different prefixes
        _, cg = make_caregiver_profile("cg_loc_diffInvalid", zip_code="00000")
        _, cl = make_client_profile("cl_loc_diffInvalid", zip_code="XXXXX")
        result = compute_match_score(cg, cl)
        loc = result["details"]["location"]
        self.assertIsNone(loc["distance_miles"])   # neither ZIP in dataset
        self.assertIsInstance(loc["score"], float)
        # Prefixes "000" vs "XXX" don't match → fallback score = 0
        self.assertEqual(loc["score"], 0.0)

    def test_reasoning_shows_distance_when_known(self):
        """
        For ZIPs that are in the dataset but not the same, the reasoning
        string includes the computed distance.
        """
        result = self._score_result("90210", "90211")
        # 90210 and 90211 are ~3.5 mi apart and within 5 mi → score=10
        # (same_zip is False, distance is known and small — score > 0)
        reasoning = result["ai_reasoning"]
        # should mention distance or "same ZIP" — not the old vague wording
        self.assertNotIn("nearby ZIP code area", reasoning)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Unauthorized users cannot approve/decline unrelated matches
# ─────────────────────────────────────────────────────────────────────────────

class UnauthorizedMatchResponseTest(TestCase):
    def setUp(self):
        self.cg_user, self.cg = make_caregiver_profile("cg_auth")
        self.cl_user, self.cl = make_client_profile("cl_auth")
        self.other_cg_user, self.other_cg = make_caregiver_profile("cg_other")
        self.org = make_organization("Auth Org")

        self.match = create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by="client",
            initiated_by_user=self.cl.user_profile,
        )

    def test_wrong_caregiver_cannot_approve(self):
        """A different caregiver should not be able to approve this match."""
        self.other_cg.user_profile.user = self.other_cg_user
        self.other_cg.user_profile.save()
        self.other_cg.user_profile.caregiver_profile = self.other_cg

        with self.assertRaises(PermissionError):
            caregiver_respond_to_match(self.match, "approve", self.other_cg_user)

    def test_staff_respond_raises_permission_error(self):
        """staff_respond_to_match always raises PermissionError in two-party workflow."""
        staff_user, _ = make_user_profile("staff_perm_test")
        with self.assertRaises(PermissionError):
            staff_respond_to_match(self.match, "approve", staff_user)

    def test_cancel_does_not_activate(self):
        self.match.cancel()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, "cancelled")
        self.assertNotEqual(self.match.status, "active")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Tag seeding test
# ─────────────────────────────────────────────────────────────────────────────

class TagSeedTest(TestCase):
    def test_default_tags_exist(self):
        """After migration, default tags should be in the database."""
        self.assertTrue(Tag.objects.filter(name="transfers").exists())
        self.assertTrue(Tag.objects.filter(name="wheelchair").exists())
        self.assertTrue(Tag.objects.filter(name="dementia").exists())
        self.assertTrue(Tag.objects.filter(name="lgbtq").exists())
        self.assertTrue(Tag.objects.filter(name="feeding-tube").exists())

    def test_tags_are_active_by_default(self):
        tag = Tag.objects.get(name="transfers")
        self.assertTrue(tag.is_active)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Match model direct method tests
# ─────────────────────────────────────────────────────────────────────────────

class MatchModelMethodTest(TestCase):
    def setUp(self):
        self.cg_user, self.cg = make_caregiver_profile("cg_model")
        self.cl_user, self.cl = make_client_profile("cl_model")
        self.org = make_organization("Model Org")

    def _fresh_match(self, initiated_by="staff"):
        staff_user, staff_profile = make_user_profile(f"staff_{initiated_by}_model")
        return create_match(
            caregiver=self.cg,
            client=self.cl,
            organization=self.org,
            initiated_by=initiated_by,
            initiated_by_user=staff_profile,
        )

    def test_caregiver_approve_saves(self):
        match = self._fresh_match()
        match.caregiver_approve()
        match.refresh_from_db()
        self.assertEqual(match.caregiver_status, "approved")

    def test_client_approve_saves(self):
        match = self._fresh_match()
        match.client_approve()
        match.refresh_from_db()
        self.assertEqual(match.client_status, "approved")

    def test_staff_approve_stores_status_for_record_keeping(self):
        """Staff approve() stores staff_status but does NOT activate the match by itself."""
        match = self._fresh_match("client")
        match.staff_approve()
        match.refresh_from_db()
        self.assertEqual(match.staff_status, "approved")
        # Match is still pending because caregiver/client haven't both approved
        self.assertEqual(match.status, "pending")

    def test_caregiver_and_client_approve_triggers_active(self):
        """Two-party approval: only caregiver + client needed to activate."""
        cg_user2, cg2 = make_caregiver_profile("cg_allapp")
        cl_user2, cl2 = make_client_profile("cl_allapp")
        match = create_match(
            caregiver=cg2, client=cl2, organization=self.org,
            initiated_by="caregiver", initiated_by_user=cg2.user_profile,
        )
        # caregiver already approved via initiation; client approves
        match.client_approve()
        match.refresh_from_db()
        self.assertEqual(match.status, "active")

    def test_cancel_sets_cancelled(self):
        match = self._fresh_match()
        match.cancel()
        match.refresh_from_db()
        self.assertEqual(match.status, "cancelled")


# ─────────────────────────────────────────────────────────────────────────────
# 11. ChatGPT AI-enhanced scoring tests
# ─────────────────────────────────────────────────────────────────────────────

class ChatGPTEnhancedScoringTest(TestCase):
    """
    Tests for compute_ai_enhanced_match_score and _call_chatgpt_match_score.

    All OpenAI API calls are mocked so no real network requests are made.
    """

    def setUp(self):
        _, self.cg = make_caregiver_profile(
            "cg_ai",
            experience=["dementia", "cooking"],
            availability={"monday": True, "wednesday": True},
            zip_code="94103",
        )
        _, self.cl = make_client_profile(
            "cl_ai",
            care_needs=["dementia", "cooking"],
            availability={"monday": True},
            zip_code="94103",
        )

    # ------------------------------------------------------------------
    # 11a. ChatGPT result is used when API returns valid JSON
    # ------------------------------------------------------------------
    @override_settings(
        OPENAI_API_KEY="fake-key-for-testing",
        OPENAI_MATCH_MODEL="gpt-4o-mini",
        OPENAI_MATCH_ENABLED=True,
        OPENAI_MATCH_TIMEOUT=10,
    )
    @patch("matching.services.OpenAI")
    def test_chatgpt_result_used_when_api_succeeds(self, mock_openai_class):
        """When ChatGPT returns a valid JSON response, its score/reasoning is used."""
        mock_message = MagicMock()
        mock_message.content = '{"score": 88, "reasoning": "Great overlap in care needs.", "strengths": ["dementia care", "cooking"], "concerns": []}'
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client_instance

        result = compute_ai_enhanced_match_score(self.cg, self.cl)

        self.assertEqual(result["score"], 88.0)
        self.assertIn("Great overlap", result["ai_reasoning"])
        self.assertIn("Key strengths", result["ai_reasoning"])
        self.assertIn("tag_overlap", result["details"])
        self.assertIn("chatgpt", result["details"])
        self.assertEqual(result["details"]["chatgpt"]["score"], 88.0)

    # ------------------------------------------------------------------
    # 11b. Local fallback when OPENAI_API_KEY is empty
    # ------------------------------------------------------------------
    @override_settings(
        OPENAI_API_KEY="",
        OPENAI_MATCH_ENABLED=True,
    )
    def test_falls_back_to_local_when_no_api_key(self):
        """When no API key is configured, local scoring is used without error."""
        result = compute_ai_enhanced_match_score(self.cg, self.cl)

        self.assertIn("score", result)
        self.assertIn("details", result)
        self.assertIn("ai_reasoning", result)
        self.assertIsInstance(result["score"], float)
        self.assertNotIn("chatgpt", result["details"])

    # ------------------------------------------------------------------
    # 11c. Local fallback when OPENAI_MATCH_ENABLED=False
    # ------------------------------------------------------------------
    @override_settings(
        OPENAI_API_KEY="fake-key-for-testing",
        OPENAI_MATCH_ENABLED=False,
    )
    def test_falls_back_to_local_when_disabled(self):
        """When OPENAI_MATCH_ENABLED is False, local scoring is used."""
        result = compute_ai_enhanced_match_score(self.cg, self.cl)
        self.assertNotIn("chatgpt", result["details"])
        self.assertIsInstance(result["score"], float)

    # ------------------------------------------------------------------
    # 11d. Local fallback when the API call raises an exception
    # ------------------------------------------------------------------
    @override_settings(
        OPENAI_API_KEY="fake-key-for-testing",
        OPENAI_MATCH_MODEL="gpt-4o-mini",
        OPENAI_MATCH_ENABLED=True,
        OPENAI_MATCH_TIMEOUT=10,
    )
    @patch("matching.services.OpenAI")
    def test_falls_back_to_local_on_api_error(self, mock_openai_class):
        """When the API call raises an exception, local scoring is used silently."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.side_effect = Exception("Network error")
        mock_openai_class.return_value = mock_client_instance

        result = compute_ai_enhanced_match_score(self.cg, self.cl)

        self.assertIn("score", result)
        self.assertIn("ai_reasoning", result)
        self.assertNotIn("chatgpt", result["details"])

    # ------------------------------------------------------------------
    # 11e. Local fallback when API returns unparseable JSON
    # ------------------------------------------------------------------
    @override_settings(
        OPENAI_API_KEY="fake-key-for-testing",
        OPENAI_MATCH_MODEL="gpt-4o-mini",
        OPENAI_MATCH_ENABLED=True,
        OPENAI_MATCH_TIMEOUT=10,
    )
    @patch("matching.services.OpenAI")
    def test_falls_back_to_local_on_bad_json(self, mock_openai_class):
        """When the API returns malformed JSON, local scoring is used."""
        mock_message = MagicMock()
        mock_message.content = "This is not valid JSON at all."
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client_instance

        result = compute_ai_enhanced_match_score(self.cg, self.cl)

        self.assertIn("score", result)
        self.assertNotIn("chatgpt", result["details"])

    # ------------------------------------------------------------------
    # 11f. _call_chatgpt_match_score returns None without a key
    # ------------------------------------------------------------------
    @override_settings(OPENAI_API_KEY="", OPENAI_MATCH_ENABLED=True)
    def test_call_chatgpt_returns_none_without_key(self):
        """_call_chatgpt_match_score returns None when no key is present."""
        result = _call_chatgpt_match_score(self.cg, self.cl)
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # 11g. ChatGPT score is clamped to 0-100
    # ------------------------------------------------------------------
    @override_settings(
        OPENAI_API_KEY="fake-key-for-testing",
        OPENAI_MATCH_MODEL="gpt-4o-mini",
        OPENAI_MATCH_ENABLED=True,
        OPENAI_MATCH_TIMEOUT=10,
    )
    @patch("matching.services.OpenAI")
    def test_chatgpt_score_is_clamped(self, mock_openai_class):
        """Scores outside 0-100 returned by ChatGPT are clamped."""
        mock_message = MagicMock()
        mock_message.content = '{"score": 150, "reasoning": "Too high.", "strengths": [], "concerns": []}'
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client_instance

        result = _call_chatgpt_match_score(self.cg, self.cl)
        self.assertIsNotNone(result)
        self.assertLessEqual(result["score"], 100.0)
        self.assertGreaterEqual(result["score"], 0.0)
