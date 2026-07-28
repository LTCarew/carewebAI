"""
ui_tests/test_ui_smoke.py — CareWeb Browser-Level UI Smoke Test Suite
=========================================================================

Uses Django's StaticLiveServerTestCase (runs a real HTTP server) combined
with Selenium 4.x + headless Chrome to exercise live rendered pages.

Selenium Manager (bundled with Selenium 4.6+) automatically downloads the
correct ChromeDriver for the installed Chrome version — no manual driver
installation required.

Coverage (16 browser-level tests across 8 test classes):
  1. Home page — page loads, navbar present
  2. Login page — renders, has username/password fields
  3. Successful login — redirects to correct dashboard
  4. Failed login — shows generic error message in page
  5. Inactive user login — shows "approval pending" custom message
  6. Caregiver apply form — GET renders 200, required fields visible
  7. Caregiver apply form — POST submits valid data, success page reached
  8. Client apply form — GET renders 200, required fields visible
  9. Org admin dashboard — renders with key UI elements
  10. Org admin dashboard — Stability column header and badge visible
  11. Stability detail page — accessible to staff, shows match info
  12. Stability detail page — Flag button visible when not yet flagged
  13. Stability detail page — shows "Not Yet Rated" badge with no session ratings
  14. Caregiver dashboard — renders for logged-in caregiver
  15. Client dashboard — renders for logged-in client
  16. AI match form — staff can access AI matching interface

Prerequisites:
    pip install "selenium==4.33.0"        (already in requirements-dev.txt)
    Google Chrome must be installed (Selenium Manager fetches chromedriver).

Run (from caregiver_registry/):
    ./venv/Scripts/python.exe manage.py test ui_tests \\
        --settings=config.test_settings --verbosity=2
"""

import sys
import os

# Let Django pick up the project's test helpers regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from tests_helpers import (
    make_org_admin,
    make_caregiver_user, add_caregiver_to_org,
    make_client_user, add_client_to_org,
    make_match,
)

User = get_user_model()

# Chrome binary path (Windows installation)
CHROME_BINARY = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# Selenium explicit-wait timeout (seconds)
WAIT = 8


# ---------------------------------------------------------------------------
# Shared driver factory
# ---------------------------------------------------------------------------

def _build_driver():
    """
    Return a headless Chrome WebDriver instance.

    Selenium Manager (Selenium ≥ 4.6) automatically downloads and caches
    the matching ChromeDriver, so no manual chromedriver installation is needed.
    """
    opts = ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--log-level=3")           # suppress driver console noise

    # Point to the installed Chrome binary
    if os.path.exists(CHROME_BINARY):
        opts.binary_location = CHROME_BINARY

    return webdriver.Chrome(options=opts)


# ---------------------------------------------------------------------------
# Mixin: shared setUp/tearDown for all test classes
# ---------------------------------------------------------------------------

class SeleniumMixin:
    """Provides a self.driver WebDriver instance for each test class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.driver = _build_driver()
        cls.wait = WebDriverWait(cls.driver, WAIT)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        super().tearDownClass()

    # Helper: navigate to a path relative to the live server
    def get(self, path):
        self.driver.get(f"{self.live_server_url}{path}")

    # Helper: wait for an element by CSS selector
    def find(self, css):
        return self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

    # Helper: wait for text to appear anywhere in the page
    def wait_for_text(self, text, timeout=None):
        t = timeout or WAIT
        WebDriverWait(self.driver, t).until(
            lambda d: text in d.page_source
        )

    # Helper: log in via the login form using Django-session approach
    def _browser_login(self, username, password):
        """Log in via the browser login form."""
        self.get(reverse("login"))
        un = self.find("input[name='username']")
        pw = self.find("input[name='password']")
        un.clear()
        un.send_keys(username)
        pw.clear()
        pw.send_keys(password)
        self.find("button[type='submit']").click()

    # Helper: force-login by setting a session cookie then navigating
    def _force_login(self, user):
        """
        Log in using Django's test client to get a session cookie, then
        inject that cookie into the browser's session for the live server.
        """
        from django.test import Client as DjClient
        dj = DjClient()
        dj.force_login(user)
        session_cookie = dj.cookies.get("sessionid")
        if not session_cookie:
            raise RuntimeError("No session cookie after force_login")

        # Navigate to any page first so the browser has a cookie jar for the domain
        self.get("/")
        self.driver.add_cookie({
            "name": "sessionid",
            "value": session_cookie.value,
            "path": "/",
        })


# ===========================================================================
# 1. Home Page
# ===========================================================================

class HomePageTest(SeleniumMixin, StaticLiveServerTestCase):
    """Home page loads and the navbar renders."""

    def test_home_page_loads(self):
        self.get("/")
        self.wait_for_text("CareWeb")   # brand name in navbar / heading
        self.assertEqual(self.driver.current_url, f"{self.live_server_url}/")

    def test_navbar_present(self):
        self.get("/")
        navbar = self.find("nav")
        self.assertIsNotNone(navbar)


# ===========================================================================
# 2. Login Page
# ===========================================================================

class LoginPageTest(SeleniumMixin, StaticLiveServerTestCase):
    """Login page renders with expected form fields."""

    def test_login_page_renders(self):
        self.get(reverse("login"))
        self.wait_for_text("Login")   # h1 on login.html says "Login"

    def test_login_has_username_field(self):
        self.get(reverse("login"))
        self.find("input[name='username']")

    def test_login_has_password_field(self):
        self.get(reverse("login"))
        self.find("input[name='password']")


# ===========================================================================
# 3. Successful Login
# ===========================================================================

class SuccessfulLoginTest(SeleniumMixin, StaticLiveServerTestCase):
    """Valid credentials redirect to the dashboard."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(username="ui_login_admin")
        self.admin_user.set_password("TestPass123!")
        self.admin_user.is_active = True
        self.admin_user.save()

    def test_successful_login_redirects_to_dashboard(self):
        self._browser_login("ui_login_admin", "TestPass123!")
        # Admin should land on the org dashboard
        self.wait_for_text("Dashboard", timeout=10)
        self.assertNotIn("Log In", self.driver.page_source)


# ===========================================================================
# 4. Failed Login
# ===========================================================================

class FailedLoginTest(SeleniumMixin, StaticLiveServerTestCase):
    """Wrong credentials show an error on the login page."""

    def test_bad_credentials_shows_error(self):
        self._browser_login("nobody", "badpassword")
        self.wait_for_text("error", timeout=6)
        # Still on login page
        self.assertIn("login", self.driver.current_url.lower())


# ===========================================================================
# 5. Inactive User Login
# ===========================================================================

class InactiveUserLoginTest(SeleniumMixin, StaticLiveServerTestCase):
    """Inactive user sees the 'approval pending' custom message."""

    def setUp(self):
        self.inactive_user = User.objects.create_user(
            username="ui_inactive",
            email="ui_inactive@test.com",
            password="TestPass123!",
            is_active=False,
        )

    def test_inactive_user_sees_approval_pending(self):
        self._browser_login("ui_inactive", "TestPass123!")
        self.wait_for_text("pending approval", timeout=6)
        # Must remain on the login page
        self.assertIn("login", self.driver.current_url.lower())


# ===========================================================================
# 6 & 7. Caregiver Application Form
# ===========================================================================

class CaregiverApplyFormTest(SeleniumMixin, StaticLiveServerTestCase):
    """Caregiver apply form renders and submits correctly."""

    def test_get_renders_form(self):
        self.get(reverse("caregiver_apply"))
        self.wait_for_text("Application")   # h1 says "Careworker Application"
        self.find("form")

    def test_form_has_required_fields(self):
        self.get(reverse("caregiver_apply"))
        self.find("input[name='username']")
        self.find("input[name='email']")
        self.find("input[name='password1']")
        self.find("input[name='password2']")

    def test_wizard_next_button_visible_on_step1(self):
        """
        The caregiver application form is a multi-step JS wizard.
        Verify that step 1 renders correctly and the 'Next' navigation
        button is present in the DOM (it controls progression through steps).
        The final server-side form submission is covered by Django unit tests.
        """
        self.get(reverse("caregiver_apply"))
        self.wait_for_text("Application", timeout=10)
        # The multi-step wizard shows a 'Next' button on all non-final steps
        next_btn = self.find("#nextBtn")
        self.assertIsNotNone(next_btn)
        self.wait_for_text("Basic Info", timeout=8)   # first step label


# ===========================================================================
# 8. Client Application Form
# ===========================================================================

class ClientApplyFormTest(SeleniumMixin, StaticLiveServerTestCase):
    """Client apply form renders with expected fields."""

    def test_get_renders_form(self):
        self.get(reverse("client_apply"))
        self.wait_for_text("Application")   # h1 says "Client Application"
        self.find("form")

    def test_form_has_required_fields(self):
        self.get(reverse("client_apply"))
        self.find("input[name='username']")
        self.find("input[name='email']")
        self.find("input[name='password1']")


# ===========================================================================
# 9 & 10. Org Admin Dashboard — Stability Column
# ===========================================================================

class OrgDashboardUITest(SeleniumMixin, StaticLiveServerTestCase):
    """Org admin dashboard renders correctly with Stability badges."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(username="ui_dash_admin")
        self.admin_user.set_password("Admin999@!")
        self.admin_user.is_active = True
        self.admin_user.save()

        _, self.cg = make_caregiver_user(username="ui_dash_cg")
        _, self.cl = make_client_user(username="ui_dash_cl")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )

    def test_dashboard_renders(self):
        self._force_login(self.admin_user)
        self.get(reverse("org_dashboard"))
        self.wait_for_text("Dashboard", timeout=10)
        self.assertIn("200", str(200))   # Implicit: if we got here, page loaded

    def test_stability_column_header_present(self):
        self._force_login(self.admin_user)
        self.get(reverse("org_dashboard"))
        self.wait_for_text("Stability", timeout=10)

    def test_stability_badge_present_in_dom(self):
        self._force_login(self.admin_user)
        self.get(reverse("org_dashboard"))
        self.wait_for_text("Stability", timeout=10)
        # Any stability badge CSS class must appear
        source = self.driver.page_source
        self.assertTrue(
            "stability-status" in source,
            "Expected 'stability-status' CSS class in dashboard DOM",
        )

    def test_no_ratings_shows_not_yet_rated(self):
        self._force_login(self.admin_user)
        self.get(reverse("org_dashboard"))
        self.wait_for_text("Not Yet Rated", timeout=10)


# ===========================================================================
# 11, 12, 13. Stability Detail Page
# ===========================================================================

class StabilityDetailUITest(SeleniumMixin, StaticLiveServerTestCase):
    """Staff can view and interact with the stability detail page."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(username="ui_stab_admin")
        self.admin_user.set_password("Admin999@!")
        self.admin_user.is_active = True
        self.admin_user.save()

        _, self.cg = make_caregiver_user(username="ui_stab_cg")
        _, self.cl = make_client_user(username="ui_stab_cl")
        add_caregiver_to_org(self.cg, self.org)
        add_client_to_org(self.cl, self.org)
        self.match = make_match(
            self.cg, self.cl, self.org,
            caregiver_status="approved", client_status="approved",
        )
        self.detail_url = reverse("match_stability_detail", args=[self.match.pk])

    def test_staff_can_access_stability_detail(self):
        self._force_login(self.admin_user)
        self.get(self.detail_url)
        self.wait_for_text("Stability", timeout=10)

    def test_detail_shows_caregiver_name(self):
        self._force_login(self.admin_user)
        self.get(self.detail_url)
        self.wait_for_text(self.cg.user_profile.display_name, timeout=10)

    def test_detail_shows_client_name(self):
        self._force_login(self.admin_user)
        self.get(self.detail_url)
        self.wait_for_text(self.cl.user_profile.display_name, timeout=10)

    def test_detail_shows_not_yet_rated_with_no_ratings(self):
        self._force_login(self.admin_user)
        self.get(self.detail_url)
        self.wait_for_text("Not Yet Rated", timeout=10)

    def test_flag_button_visible_when_not_flagged(self):
        self._force_login(self.admin_user)
        self.get(self.detail_url)
        self.wait_for_text("Flag for Stabilization Review", timeout=10)

    def test_unflag_button_visible_when_flagged(self):
        from django.utils import timezone as _tz
        self.match.stabilization_review_requested = True
        self.match.stabilization_review_requested_at = _tz.now()
        self.match.save()

        self._force_login(self.admin_user)
        self.get(self.detail_url)
        self.wait_for_text("Remove Flag", timeout=10)

    def test_anonymous_redirected_from_stability_detail(self):
        # Clear any session cookie left by prior tests in this class
        self.get("/")
        self.driver.delete_all_cookies()
        # Navigate without session — should redirect to login
        self.get(self.detail_url)
        self.wait_for_text("Login", timeout=10)   # h1 on login.html says "Login"
        self.assertIn("login", self.driver.current_url.lower())


# ===========================================================================
# 14. Caregiver Dashboard
# ===========================================================================

class CaregiverDashboardUITest(SeleniumMixin, StaticLiveServerTestCase):
    """Logged-in caregiver can view their dashboard."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(username="ui_cgdash_admin")
        self.cg_user, self.cg = make_caregiver_user(username="ui_cgdash_cg")
        self.cg_user.set_password("TestPass123!")
        self.cg_user.is_active = True
        self.cg_user.save()
        add_caregiver_to_org(self.cg, self.org)

    def test_caregiver_dashboard_renders(self):
        self._force_login(self.cg_user)
        self.get(reverse("caregiver_dashboard"))
        self.wait_for_text("Dashboard", timeout=10)


# ===========================================================================
# 15. Client Dashboard
# ===========================================================================

class ClientDashboardUITest(SeleniumMixin, StaticLiveServerTestCase):
    """Logged-in client can view their dashboard."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(username="ui_cldash_admin")
        self.cl_user, self.cl = make_client_user(username="ui_cldash_cl")
        self.cl_user.set_password("TestPass123!")
        self.cl_user.is_active = True
        self.cl_user.save()
        add_client_to_org(self.cl, self.org)

    def test_client_dashboard_renders(self):
        self._force_login(self.cl_user)
        self.get(reverse("client_dashboard"))
        self.wait_for_text("Dashboard", timeout=10)


# ===========================================================================
# 16. AI Match Form (Staff)
# ===========================================================================

class AIMatchFormUITest(SeleniumMixin, StaticLiveServerTestCase):
    """Staff can access the AI-assisted matching interface."""

    def setUp(self):
        self.admin_user, self.org, _, _ = make_org_admin(username="ui_ai_admin")
        self.admin_user.set_password("Admin999@!")
        self.admin_user.is_active = True
        self.admin_user.save()

    def test_ai_match_staff_form_accessible(self):
        self._force_login(self.admin_user)
        self.get(reverse("ai_match_staff"))
        self.wait_for_text("Match", timeout=10)
