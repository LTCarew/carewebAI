"""
Tests for the Stability Snapshot feature.

Covers:
  - get_stability_snapshot() logic (green / yellow / red)
  - No-ratings path returns "Not Yet Rated" (status="none") regardless of match_score
  - Match compatibility score (match_score) NEVER drives stability status
  - Deterministic results across repeated calls
  - Signal labels are populated
  - Dashboard: staff sees Stability column with text labels
  - Flag action: authorized staff can flag, duplicate prevented, timestamp stored
  - Permissions: caregiver / client / other-org staff receive 302 redirect, not 200
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date

from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth import get_user_model

from tests_helpers import (
    make_org_admin, make_staff_user,
    make_caregiver_user, add_caregiver_to_org,
    make_client_user, add_client_to_org,
    make_match, make_schedule, make_schedule_entry,
)

User = get_user_model()


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_rating(entry, rater_profile, rater_role="client", value=8):
    """Create a ScheduleEntryRating with all four metrics set to `value`."""
    from registry.models import ScheduleEntryRating
    return ScheduleEntryRating.objects.create(
        schedule_entry=entry,
        rater_profile=rater_profile,
        rater_role=rater_role,
        rating_date=date.today(),
        care_fit_respect=value,
        communication_coordination=value,
        reliability_consistency=value,
        workload_support_balance=value,
        notes="Test rating",
    )


def _approve_entry(entry):
    """Mark a ScheduleEntry fully approved so it can be rated."""
    entry.caregiver_status = "approved"
    entry.support_person_status = "approved"
    entry.save()
    return entry


def _make_approved_schedule(org, cl_profile, cg_profile, match):
    """Create a minimal approved Schedule for rating tests."""
    from registry.models import Schedule
    return Schedule.objects.create(
        organization=org,
        client=cl_profile,
        caregiver=cg_profile,
        match=match,
        status="approved",
        start_date=date.today(),
        frequency="weekly",
        created_by=cl_profile.user_profile,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. Stability logic — rating-based path
# ══════════════════════════════════════════════════════════════════════════════

class StabilityFromRatingsGreenTest(TestCase):
    """Average rating ≥ 7.5 → Green / Stable."""

    def setUp(self):
        # make_org_admin returns (user, org, staff_profile, org_staff)
        self.admin_user, self.org, self.staff_profile, _ = make_org_admin(
            username="sa_admin_g", org_name="Org G"
        )
        _, self.cg = make_caregiver_user(username="sa_cg_g")
        _, self.cl = make_client_user(username="sa_cl_g")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        schedule = _make_approved_schedule(self.org, self.cl, self.cg, self.match)
        self.entry = _approve_entry(make_schedule_entry(schedule))
        # All ratings = 9 → avg 9.0 ≥ 7.5 → green
        _make_rating(self.entry, self.cl.user_profile, rater_role="client", value=9)

    def test_status_is_green(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["status"], "green")

    def test_label_is_stable(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["label"], "Stable")

    def test_score_is_90(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["score"], 90)

    def test_signals_present(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        signals = snap["signals"]
        self.assertIn("schedule_consistency", signals)
        self.assertIn("travel_burden", signals)
        self.assertIn("access_alignment", signals)
        self.assertIn("care_continuity", signals)
        self.assertIn("support_flags", signals)

    def test_schedule_consistency_good(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["signals"]["schedule_consistency"], "Good")

    def test_explanation_is_string(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertIsInstance(snap["explanation"], str)
        self.assertGreater(len(snap["explanation"]), 20)

    def test_source_is_ratings(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["source"], "ratings")

    def test_deterministic(self):
        """Same data → same result every call (no randomness at render time)."""
        from matching.stability import get_stability_snapshot
        snap1 = get_stability_snapshot(self.match)
        snap2 = get_stability_snapshot(self.match)
        self.assertEqual(snap1["status"], snap2["status"])
        self.assertEqual(snap1["score"], snap2["score"])


class StabilityFromRatingsYellowTest(TestCase):
    """Average rating ≥ 5.0 and < 7.5 → Yellow / Monitor."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="sa_admin_y", org_name="Org Y"
        )
        _, self.cg = make_caregiver_user(username="sa_cg_y")
        _, self.cl = make_client_user(username="sa_cl_y")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        schedule = _make_approved_schedule(self.org, self.cl, self.cg, self.match)
        self.entry = _approve_entry(make_schedule_entry(schedule))
        # All ratings = 6 → avg 6.0 ≥ 5.0 but < 7.5 → yellow
        _make_rating(self.entry, self.cl.user_profile, rater_role="client", value=6)

    def test_status_is_yellow(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["status"], "yellow")

    def test_label_is_monitor(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["label"], "Monitor")


class StabilityFromRatingsRedTest(TestCase):
    """Average rating < 5.0 → Red / At Risk."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="sa_admin_r", org_name="Org R"
        )
        _, self.cg = make_caregiver_user(username="sa_cg_r")
        _, self.cl = make_client_user(username="sa_cl_r")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        schedule = _make_approved_schedule(self.org, self.cl, self.cg, self.match)
        self.entry = _approve_entry(make_schedule_entry(schedule))
        # All ratings = 3 → avg 3.0 < 5.0 → red
        _make_rating(self.entry, self.cl.user_profile, rater_role="client", value=3)

    def test_status_is_red(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["status"], "red")

    def test_label_is_at_risk(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["label"], "At Risk")

    def test_care_continuity_frequent_disruption(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["signals"]["care_continuity"], "Frequent disruption")

    def test_schedule_consistency_poor(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["signals"]["schedule_consistency"], "Poor")


# ══════════════════════════════════════════════════════════════════════════════
# 2. No ratings — "Not Yet Rated" path
#    The match compatibility score (match_score) MUST NOT drive stability.
# ══════════════════════════════════════════════════════════════════════════════

class StabilityNoRatingsTest(TestCase):
    """
    When no ScheduleEntryRatings exist, the snapshot is always 'Not Yet Rated'
    regardless of the match_score value.

    This is the critical correctness guarantee: stability is based on lived
    experience (ratings), never on pre-appointment compatibility scores.
    """

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="sa_admin_nr", org_name="Org NR"
        )
        _, self.cg = make_caregiver_user(username="sa_cg_nr")
        _, self.cl = make_client_user(username="sa_cl_nr")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)

    def _make_match_with_score(self, score):
        from matching.models import Match
        return Match.objects.create(
            organization=self.org,
            caregiver=self.cg,
            client=self.cl,
            initiated_by="staff",
            caregiver_status="approved",
            client_status="approved",
            status="active",
            match_score=score,
            match_details={},
            ai_reasoning="test",
        )

    def test_high_score_still_gives_not_yet_rated(self):
        """match_score=80 with no ratings → Not Yet Rated, NOT green."""
        from matching.stability import get_stability_snapshot
        match = self._make_match_with_score(80)
        snap = get_stability_snapshot(match)
        self.assertEqual(snap["status"], "none")
        self.assertEqual(snap["label"], "Not Yet Rated")

    def test_mid_score_still_gives_not_yet_rated(self):
        """match_score=55 with no ratings → Not Yet Rated, NOT yellow."""
        from matching.stability import get_stability_snapshot
        match = self._make_match_with_score(55)
        snap = get_stability_snapshot(match)
        self.assertEqual(snap["status"], "none")
        self.assertEqual(snap["label"], "Not Yet Rated")

    def test_low_score_still_gives_not_yet_rated(self):
        """match_score=25 with no ratings → Not Yet Rated, NOT red."""
        from matching.stability import get_stability_snapshot
        match = self._make_match_with_score(25)
        snap = get_stability_snapshot(match)
        self.assertEqual(snap["status"], "none")
        self.assertEqual(snap["label"], "Not Yet Rated")

    def test_none_score_still_gives_not_yet_rated(self):
        """match_score=None with no ratings → Not Yet Rated."""
        from matching.stability import get_stability_snapshot
        from matching.models import Match
        match = Match.objects.create(
            organization=self.org,
            caregiver=self.cg,
            client=self.cl,
            initiated_by="staff",
            caregiver_status="approved",
            client_status="approved",
            status="active",
            match_score=None,
        )
        snap = get_stability_snapshot(match)
        self.assertEqual(snap["status"], "none")
        self.assertEqual(snap["label"], "Not Yet Rated")
        self.assertIsNone(snap["score"])

    def test_no_ratings_source_is_no_ratings(self):
        from matching.stability import get_stability_snapshot
        match = self._make_match_with_score(80)
        snap = get_stability_snapshot(match)
        self.assertEqual(snap["source"], "no_ratings")

    def test_no_ratings_score_is_none(self):
        from matching.stability import get_stability_snapshot
        match = self._make_match_with_score(80)
        snap = get_stability_snapshot(match)
        self.assertIsNone(snap["score"])

    def test_no_ratings_signals_use_not_yet_rated(self):
        """Rating-derived signals must show 'Not yet rated', not guesses."""
        from matching.stability import get_stability_snapshot
        match = self._make_match_with_score(90)
        snap = get_stability_snapshot(match)
        self.assertEqual(snap["signals"]["schedule_consistency"], "Not yet rated")
        self.assertEqual(snap["signals"]["access_alignment"], "Not yet rated")
        self.assertEqual(snap["signals"]["care_continuity"], "Not yet rated")

    def test_no_ratings_travel_burden_still_shown(self):
        """Travel burden (geographic distance) is factual and shown even without ratings."""
        from matching.stability import get_stability_snapshot
        from matching.models import Match
        match = Match.objects.create(
            organization=self.org,
            caregiver=self.cg,
            client=self.cl,
            initiated_by="staff",
            caregiver_status="approved",
            client_status="approved",
            status="active",
            match_score=None,
            match_details={"location": {"distance_miles": 3.0}},
        )
        snap = get_stability_snapshot(match)
        # travel_burden is shown from real distance, not blocked by "not yet rated"
        self.assertEqual(snap["signals"]["travel_burden"], "Low")

    def test_no_ratings_no_error(self):
        """Missing ratings must not raise an exception."""
        from matching.stability import get_stability_snapshot
        match = self._make_match_with_score(60)
        try:
            get_stability_snapshot(match)
        except Exception as exc:
            self.fail(f"get_stability_snapshot raised unexpectedly: {exc}")

    def test_no_ratings_explanation_mentions_ratings(self):
        """Explanation must mention ratings, not match score."""
        from matching.stability import get_stability_snapshot
        match = self._make_match_with_score(85)
        snap = get_stability_snapshot(match)
        explanation = snap["explanation"].lower()
        self.assertIn("rating", explanation)
        self.assertNotIn("compatibility", explanation)
        self.assertNotIn("match score", explanation)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Review flag status override
# ══════════════════════════════════════════════════════════════════════════════

class StabilityReviewFlagTest(TestCase):
    """stabilization_review_requested=True forces support_flags to 'Immediate review recommended'."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="sa_admin_fl", org_name="Org FL"
        )
        _, self.cg = make_caregiver_user(username="sa_cg_fl")
        _, self.cl = make_client_user(username="sa_cl_fl")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        self.match.stabilization_review_requested = True
        self.match.save()

    def test_support_flags_overridden_to_immediate(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertEqual(snap["signals"]["support_flags"], "Immediate review recommended")

    def test_review_requested_is_true(self):
        from matching.stability import get_stability_snapshot
        snap = get_stability_snapshot(self.match)
        self.assertTrue(snap["review_requested"])


# ══════════════════════════════════════════════════════════════════════════════
# 4. Staff Dashboard — Stability column rendering
# ══════════════════════════════════════════════════════════════════════════════

class OrgDashboardStabilityColumnTest(TestCase):
    """Staff dashboard includes Stability column for active matches."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="sa_dash_admin", org_name="Org Dash"
        )
        _, self.cg = make_caregiver_user(username="sa_dash_cg")
        _, self.cl = make_client_user(username="sa_cl_dash")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        # Set a high match_score to confirm it does NOT affect the stability label
        self.match.match_score = 85
        self.match.save()

        self.c = TestClient()
        self.c.force_login(self.admin_user)

    def test_stability_column_header_present(self):
        resp = self.c.get(reverse("org_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Stability")

    def test_stability_label_present(self):
        """Any valid stability label — including 'Not Yet Rated' — should appear."""
        resp = self.c.get(reverse("org_dashboard"))
        content = resp.content.decode()
        self.assertTrue(
            "Stable" in content
            or "Monitor" in content
            or "At Risk" in content
            or "Not Yet Rated" in content,
            "Expected at least one stability label in response",
        )

    def test_no_ratings_shows_not_yet_rated(self):
        """With no session ratings, the stability badge must say 'Not Yet Rated'."""
        resp = self.c.get(reverse("org_dashboard"))
        self.assertContains(resp, "Not Yet Rated")

    def test_high_match_score_does_not_produce_green(self):
        """match_score=85 with no ratings must NOT produce a green Stable badge."""
        resp = self.c.get(reverse("org_dashboard"))
        content = resp.content.decode()
        # "Stable" should NOT appear (no real ratings to justify it)
        self.assertNotIn("stability-status--green", content)

    def test_stability_status_css_class_present(self):
        resp = self.c.get(reverse("org_dashboard"))
        self.assertContains(resp, "stability-status")

    def test_not_yet_rated_css_class_present(self):
        """The neutral CSS class must appear when no ratings exist."""
        resp = self.c.get(reverse("org_dashboard"))
        self.assertContains(resp, "stability-status--none")

    def test_no_stability_column_on_caregiver_dashboard(self):
        """Stability CSS classes must NOT appear on the caregiver dashboard."""
        cg_client = TestClient()
        cg_client.force_login(self.cg.user_profile.user)
        resp = cg_client.get(reverse("caregiver_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "stability-status--green")
        self.assertNotContains(resp, "stability-status--red")


# ══════════════════════════════════════════════════════════════════════════════
# 5. Flag for Stabilization Review — authorized staff
# ══════════════════════════════════════════════════════════════════════════════

class FlagStabilizationReviewTest(TestCase):
    """Authorized org-admin staff can flag a match."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="fl_admin", org_name="Org Flag"
        )
        _, self.cg = make_caregiver_user(username="fl_cg")
        _, self.cl = make_client_user(username="fl_cl")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        self.c = TestClient()
        self.c.force_login(self.admin_user)
        self.flag_url = reverse("flag_stabilization_review", args=[self.match.pk])

    def test_flag_sets_requested_true(self):
        resp = self.c.post(self.flag_url)
        self.assertIn(resp.status_code, [200, 302])
        self.match.refresh_from_db()
        self.assertTrue(self.match.stabilization_review_requested)

    def test_flag_stores_timestamp(self):
        self.c.post(self.flag_url)
        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.stabilization_review_requested_at)

    def test_flag_stores_requester(self):
        self.c.post(self.flag_url)
        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.stabilization_review_requested_by)

    def test_duplicate_flag_is_idempotent(self):
        """Second POST to already-flagged match keeps flag set and does not error."""
        self.c.post(self.flag_url)
        resp = self.c.post(self.flag_url)
        self.assertIn(resp.status_code, [200, 302])
        self.match.refresh_from_db()
        self.assertTrue(self.match.stabilization_review_requested)

    def test_get_method_redirects(self):
        """GET to the flag URL must redirect (POST-only action)."""
        resp = self.c.get(self.flag_url)
        self.assertEqual(resp.status_code, 302)


# ══════════════════════════════════════════════════════════════════════════════
# 6. Permissions — unauthorized users cannot flag
# ══════════════════════════════════════════════════════════════════════════════

class FlagStabilizationPermissionsTest(TestCase):
    """Non-staff and cross-org users cannot flag a match."""

    def setUp(self):
        # Primary org + match
        self.admin_user, self.org, _, _ = make_org_admin(
            username="perm_admin", org_name="Org Perm"
        )
        _, self.cg = make_caregiver_user(username="perm_cg")
        _, self.cl = make_client_user(username="perm_cl")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        self.flag_url = reverse("flag_stabilization_review", args=[self.match.pk])

        # Second org admin (different org)
        self.admin2_user, self.org2, _, _ = make_org_admin(
            username="perm_admin2", org_name="Org Perm2"
        )

    def test_caregiver_cannot_flag(self):
        c = TestClient()
        c.force_login(self.cg.user_profile.user)
        resp = c.post(self.flag_url, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.match.refresh_from_db()
        self.assertFalse(self.match.stabilization_review_requested)

    def test_client_cannot_flag(self):
        c = TestClient()
        c.force_login(self.cl.user_profile.user)
        resp = c.post(self.flag_url, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.match.refresh_from_db()
        self.assertFalse(self.match.stabilization_review_requested)

    def test_anonymous_cannot_flag(self):
        c = TestClient()
        resp = c.post(self.flag_url, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.match.refresh_from_db()
        self.assertFalse(self.match.stabilization_review_requested)

    def test_other_org_staff_cannot_flag(self):
        """Staff of a different org must not be able to flag this match."""
        c = TestClient()
        c.force_login(self.admin2_user)
        resp = c.post(self.flag_url, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.match.refresh_from_db()
        self.assertFalse(self.match.stabilization_review_requested)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Travel burden signal from match_details.location.distance_miles
# ══════════════════════════════════════════════════════════════════════════════

class TravelBurdenSignalTest(TestCase):
    """_travel_burden_from_match derives correct label from distance_miles."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="tb_admin", org_name="Org TB"
        )
        _, self.cg = make_caregiver_user(username="tb_cg")
        _, self.cl = make_client_user(username="tb_cl")

    def _unsaved_match(self, distance):
        from matching.models import Match
        return Match(
            organization=self.org,
            caregiver=self.cg,
            client=self.cl,
            match_details={"location": {"distance_miles": distance}},
            match_score=None,
            stabilization_review_requested=False,
        )

    def test_low_travel_within_5_miles(self):
        from matching.stability import _travel_burden_from_match
        m = self._unsaved_match(3.0)
        self.assertEqual(_travel_burden_from_match(m), "Low")

    def test_moderate_travel_within_20_miles(self):
        from matching.stability import _travel_burden_from_match
        m = self._unsaved_match(15.0)
        self.assertEqual(_travel_burden_from_match(m), "Moderate")

    def test_high_travel_over_20_miles(self):
        from matching.stability import _travel_burden_from_match
        m = self._unsaved_match(25.0)
        self.assertEqual(_travel_burden_from_match(m), "High")

    def test_none_distance_returns_moderate(self):
        from matching.stability import _travel_burden_from_match
        m = self._unsaved_match(None)
        self.assertEqual(_travel_burden_from_match(m), "Moderate")


# ══════════════════════════════════════════════════════════════════════════════
# 8. Stability Detail page — access control and content
# ══════════════════════════════════════════════════════════════════════════════

class StabilityDetailViewTest(TestCase):
    """
    Staff can access the stability detail page.
    Caregiver, client, and anonymous users cannot.
    """

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="sd_admin", org_name="Org SD"
        )
        _, self.cg = make_caregiver_user(username="sd_cg")
        _, self.cl = make_client_user(username="sd_cl")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        # Set a high match_score to confirm it does NOT create a green badge
        self.match.match_score = 80
        self.match.save()
        self.detail_url = reverse("match_stability_detail", args=[self.match.pk])

    def test_staff_can_access(self):
        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertEqual(resp.status_code, 200)

    def test_page_contains_caregiver_name(self):
        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertContains(resp, self.cg.user_profile.display_name)

    def test_page_contains_client_name(self):
        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertContains(resp, self.cl.user_profile.display_name)

    def test_page_shows_not_yet_rated_when_no_ratings(self):
        """With no session ratings the detail page must show 'Not Yet Rated'."""
        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertContains(resp, "Not Yet Rated")

    def test_high_match_score_does_not_show_stable(self):
        """match_score=80 with no ratings must NOT show 'Stable' on detail page."""
        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertNotContains(resp, "stability-status--green")

    def test_page_shows_flag_button_when_not_flagged(self):
        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertContains(resp, "Flag for Stabilization Review")

    def test_page_shows_unflag_button_when_flagged(self):
        self.match.stabilization_review_requested = True
        self.match.save()
        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertContains(resp, "Remove Flag")

    def test_caregiver_redirected(self):
        c = TestClient()
        c.force_login(self.cg.user_profile.user)
        resp = c.get(self.detail_url, follow=False)
        self.assertEqual(resp.status_code, 302)

    def test_client_redirected(self):
        c = TestClient()
        c.force_login(self.cl.user_profile.user)
        resp = c.get(self.detail_url, follow=False)
        self.assertEqual(resp.status_code, 302)

    def test_anonymous_redirected(self):
        c = TestClient()
        resp = c.get(self.detail_url, follow=False)
        self.assertEqual(resp.status_code, 302)

    def test_page_shows_session_rating_history_when_ratings_exist(self):
        """When an approved schedule + ratings exist, the session history section renders."""
        from registry.models import Schedule
        schedule = Schedule.objects.create(
            organization=self.org,
            client=self.cl,
            caregiver=self.cg,
            match=self.match,
            status="approved",
            start_date=date.today(),
            frequency="weekly",
            created_by=self.cl.user_profile,
        )
        entry = _approve_entry(make_schedule_entry(schedule))
        _make_rating(entry, self.cl.user_profile, rater_role="client", value=8)
        _make_rating(entry, self.cg.user_profile, rater_role="caregiver", value=7)

        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Session Rating History")

    def test_page_shows_stable_when_ratings_are_high(self):
        """After real high ratings are added, detail page shows 'Stable'."""
        from registry.models import Schedule
        schedule = Schedule.objects.create(
            organization=self.org,
            client=self.cl,
            caregiver=self.cg,
            match=self.match,
            status="approved",
            start_date=date.today(),
            frequency="weekly",
            created_by=self.cl.user_profile,
        )
        entry = _approve_entry(make_schedule_entry(schedule))
        _make_rating(entry, self.cl.user_profile, rater_role="client", value=9)

        c = TestClient()
        c.force_login(self.admin_user)
        resp = c.get(self.detail_url)
        self.assertContains(resp, "Stable")


# ══════════════════════════════════════════════════════════════════════════════
# 9. Unflag Stabilization Review
# ══════════════════════════════════════════════════════════════════════════════

class UnflagStabilizationReviewTest(TestCase):
    """Staff can unflag a previously flagged match."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(
            username="uf_admin", org_name="Org UF"
        )
        _, self.cg = make_caregiver_user(username="uf_cg")
        _, self.cl = make_client_user(username="uf_cl")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        # Pre-flag the match
        from django.utils import timezone as _tz
        self.match.stabilization_review_requested = True
        self.match.stabilization_review_requested_at = _tz.now()
        self.match.stabilization_review_requested_by = self.admin_user.profile
        self.match.save()

        self.c = TestClient()
        self.c.force_login(self.admin_user)
        self.unflag_url = reverse("unflag_stabilization_review", args=[self.match.pk])

    def test_unflag_clears_flag(self):
        resp = self.c.post(self.unflag_url)
        self.assertIn(resp.status_code, [200, 302])
        self.match.refresh_from_db()
        self.assertFalse(self.match.stabilization_review_requested)

    def test_unflag_clears_timestamp(self):
        self.c.post(self.unflag_url)
        self.match.refresh_from_db()
        self.assertIsNone(self.match.stabilization_review_requested_at)

    def test_unflag_clears_requester(self):
        self.c.post(self.unflag_url)
        self.match.refresh_from_db()
        self.assertIsNone(self.match.stabilization_review_requested_by)

    def test_unflag_on_already_unflagged_match_is_safe(self):
        """POSTing unflag when not flagged should not error."""
        self.match.stabilization_review_requested = False
        self.match.save()
        resp = self.c.post(self.unflag_url)
        self.assertIn(resp.status_code, [200, 302])

    def test_get_method_redirects(self):
        """GET to the unflag URL must redirect (POST-only action)."""
        resp = self.c.get(self.unflag_url)
        self.assertEqual(resp.status_code, 302)

    def test_caregiver_cannot_unflag(self):
        c = TestClient()
        c.force_login(self.cg.user_profile.user)
        resp = c.post(self.unflag_url, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.match.refresh_from_db()
        self.assertTrue(self.match.stabilization_review_requested)

    def test_client_cannot_unflag(self):
        c = TestClient()
        c.force_login(self.cl.user_profile.user)
        resp = c.post(self.unflag_url, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.match.refresh_from_db()
        self.assertTrue(self.match.stabilization_review_requested)
