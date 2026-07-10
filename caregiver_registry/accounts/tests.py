"""
accounts/tests.py — Django TestCase view tests for authentication and org signup.

Covers:
  - GET/POST /signup/organization/
  - Login with valid credentials (redirect through dashboard_redirect)
  - Login with inactive account (custom approval-pending error)
  - Authenticated user hitting org signup redirects away
  - Unauthenticated access to protected pages redirects to login
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth import get_user_model

from tests_helpers import make_org_admin, make_caregiver_user, make_client_user

User = get_user_model()

PASSWORD = "TestPass123!"


# ─────────────────────────────────────────────────────────────────────────────
# Org Admin Signup
# ─────────────────────────────────────────────────────────────────────────────

class OrgSignupViewGetTest(TestCase):
    """GET /signup/organization/ should render the signup form."""

    def setUp(self):
        self.client = TestClient()
        self.url = reverse("organization_signup")

    def test_get_renders_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_get_contains_org_fields(self):
        response = self.client.get(self.url)
        self.assertContains(response, "organization_name")

    def test_authenticated_user_is_redirected(self):
        """Already logged-in users must be redirected away from the signup page."""
        admin_user, _, _, _ = make_org_admin(username="existingadmin")
        self.client.force_login(admin_user)
        response = self.client.get(self.url)
        # Should redirect to dashboard (not stay on signup)
        self.assertIn(response.status_code, [301, 302])


class OrgSignupViewPostTest(TestCase):
    """POST /signup/organization/ with valid data creates org and redirects."""

    def setUp(self):
        self.client = TestClient()
        self.url = reverse("organization_signup")
        self.valid_data = {
            "organization_name": "New Care Org",
            "organization_city": "Oakland",
            "organization_zip_code": "94601",
            "organization_contact_email": "org@newcare.example",
            "first_name": "Alice",
            "last_name": "Admin",
            "username": "aliceadmin",
            "email": "alice@newcare.example",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }

    def test_post_valid_creates_user(self):
        self.client.post(self.url, self.valid_data)
        self.assertTrue(User.objects.filter(username="aliceadmin").exists())

    def test_post_valid_redirects_to_org_dashboard(self):
        response = self.client.post(self.url, self.valid_data)
        self.assertRedirects(response, reverse("org_dashboard"))

    def test_post_duplicate_username_shows_error(self):
        make_org_admin(username="aliceadmin")
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already in use")

    def test_post_duplicate_email_shows_error(self):
        data = self.valid_data.copy()
        # Create a user with the same email
        User.objects.create_user(
            username="otheralice",
            email="alice@newcare.example",
            password=PASSWORD,
        )
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already in use")

    def test_post_password_mismatch_shows_error(self):
        data = self.valid_data.copy()
        data["password2"] = "WrongPassword!"
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "do not match")


# ─────────────────────────────────────────────────────────────────────────────
# Login — valid credentials
# ─────────────────────────────────────────────────────────────────────────────

class LoginViewTest(TestCase):
    """POST /login/ with valid credentials redirects to the appropriate dashboard."""

    def setUp(self):
        self.client = TestClient()
        self.url = reverse("login")

    def test_login_page_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_valid_org_admin_login_redirects(self):
        admin_user, _, _, _ = make_org_admin(username="loginadmin")
        response = self.client.post(self.url, {
            "username": "loginadmin",
            "password": PASSWORD,
        })
        # Should redirect — either to next or to default redirect
        self.assertIn(response.status_code, [301, 302])

    def test_valid_caregiver_login_redirects(self):
        cg_user, _ = make_caregiver_user(username="logincg")
        # Caregivers are created with is_active=True in make_caregiver_user
        response = self.client.post(self.url, {
            "username": "logincg",
            "password": PASSWORD,
        })
        self.assertIn(response.status_code, [301, 302])

    def test_invalid_credentials_shows_error(self):
        response = self.client.post(self.url, {
            "username": "nonexistent",
            "password": "wrongpass",
        })
        self.assertEqual(response.status_code, 200)
        # Should not crash — form re-renders with error
        self.assertContains(response, "error")  # generic check


# ─────────────────────────────────────────────────────────────────────────────
# Login — inactive account (approval pending)
# ─────────────────────────────────────────────────────────────────────────────

class InactiveUserLoginTest(TestCase):
    """
    Inactive users (awaiting org approval) should see a friendly error message
    and NOT be logged in. The app uses CareWebLoginForm.confirm_login_allowed
    to produce this message.
    """

    def setUp(self):
        self.client = TestClient()
        self.url = reverse("login")
        # Caregiver applicants are created with is_active=False
        self.inactive_user, _ = make_caregiver_user(username="inactivecg", is_active=False)

    def test_inactive_user_sees_approval_pending_message(self):
        response = self.client.post(self.url, {
            "username": "inactivecg",
            "password": PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pending approval")

    def test_inactive_user_is_not_logged_in(self):
        self.client.post(self.url, {
            "username": "inactivecg",
            "password": PASSWORD,
        })
        # If user were logged in, session would have _auth_user_id
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_no_server_error(self):
        """Regression: inactive user must not cause a 500."""
        response = self.client.post(self.url, {
            "username": "inactivecg",
            "password": PASSWORD,
        })
        self.assertNotEqual(response.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Access control — unauthenticated
# ─────────────────────────────────────────────────────────────────────────────

class UnauthenticatedAccessTest(TestCase):
    """Protected views must redirect unauthenticated users to login."""

    def setUp(self):
        self.client = TestClient()

    def _assert_redirects_to_login(self, url):
        response = self.client.get(url)
        self.assertIn(response.status_code, [301, 302])
        location = response.get("Location", "")
        self.assertIn("login", location)

    def test_dashboard_requires_login(self):
        self._assert_redirects_to_login(reverse("dashboard_redirect"))

    def test_caregiver_dashboard_requires_login(self):
        self._assert_redirects_to_login(reverse("caregiver_dashboard"))

    def test_client_dashboard_requires_login(self):
        self._assert_redirects_to_login(reverse("client_dashboard"))

    def test_org_dashboard_requires_login(self):
        self._assert_redirects_to_login(reverse("org_dashboard"))

    def test_registry_network_requires_login(self):
        self._assert_redirects_to_login(reverse("registry_network"))

    def test_coordinator_dashboard_requires_login(self):
        self._assert_redirects_to_login(reverse("coordinator_dashboard"))
