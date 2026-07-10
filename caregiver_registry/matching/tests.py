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
# 8. Unauthorized users cannot approve/decline unrelated matches
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
