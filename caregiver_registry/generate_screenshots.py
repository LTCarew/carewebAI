"""
Capture presentation-ready CareWeb user-journey screenshots.

This is deliberately a standalone Django/Selenium runner rather than a test
case. It creates an isolated test database, loads the real CIL-Care demo data,
starts Django's live test server, logs in as each persona, and saves screenshots
plus a JSON manifest containing plain-language captions.

Run from caregiver_registry/:
    venv/Scripts/python.exe generate_screenshots.py

Output:
    screenshots/careworker/*.png
    screenshots/staff_admin/*.png
    screenshots/client/*.png
    screenshots/support_person/*.png
    screenshots/manifest.json
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Ensure imports work when this file is launched from either the repository root
# or caregiver_registry/.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.test_settings")

import django

django.setup()

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.test import override_settings

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from matching.models import Match
from registry.models import Schedule, ScheduleEntry


OUTPUT_DIR = BASE_DIR / "screenshots"
CHROME_BINARY = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PASSWORD = "cil-projects@thecil.org"
MAX_FULL_PAGE_HEIGHT = 15000
VIEWPORT_WIDTH = 1440
VIEWPORT_HEIGHT = 900


def _build_driver():
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--hide-scrollbars")
    options.add_argument(f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--log-level=3")
    if os.path.exists(CHROME_BINARY):
        options.binary_location = CHROME_BINARY
    return webdriver.Chrome(options=options)


def _safe_filename(value):
    return "".join(c.lower() if c.isalnum() else "_" for c in value).strip("_")


class JourneyCapture(StaticLiveServerTestCase):
    """Use Django's test DB/live server while producing artifacts, not asserts."""

    @classmethod
    def _setup_coordinator_invite(cls):
        """Create a CoordinatorInvite for the demo client for the support-person journey."""
        from registry.models import CoordinatorInvite
        from django.utils import timezone
        import uuid
        try:
            client_profile = cls.client_user.profile.client_profile
            cls.coordinator_invite = CoordinatorInvite.objects.create(
                client_profile=client_profile,
                email="demo-coordinator@example.com",
                invited_by=cls.client_user,
                token=uuid.uuid4(),
                expires_at=timezone.now() + timezone.timedelta(days=7),
            )
        except Exception as exc:
            print(f"  [coordinator invite setup skipped: {exc}]")
            cls.coordinator_invite = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The normal test settings deliberately disable network calls. The
        # presentation capture is the one explicit exception: enable the
        # ChatGPT enhancement only for this isolated run, without changing
        # the test suite or storing a key in source control.
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for the presentation capture. "
                "Set it in caregiver_registry/.env and do not commit it."
            )
        cls._openai_override = override_settings(
            OPENAI_MATCH_ENABLED=True,
            OPENAI_API_KEY=api_key,
        )
        cls._openai_override.enable()
        # The command is idempotent and gives us realistic profiles, active
        # matches, approved schedules, historical ratings, and stability states.
        call_command("seed_cil_care", count=9, clear=True, verbosity=0)
        cls.driver = _build_driver()
        cls.wait = WebDriverWait(cls.driver, 12)

        cls.admin = get_user_model().objects.get(email="cil-projects@thecil.org")
        cls.careworker = get_user_model().objects.get(email="cilcg1@example.com")
        cls.client_user = get_user_model().objects.get(email="cilcl1@example.com")
        cls.match = Match.objects.filter(
            caregiver__user_profile__user=cls.careworker,
            client__user_profile__user=cls.client_user,
        ).first()
        if not cls.match:
            raise RuntimeError("Seeded careworker/client match could not be found")
        cls.schedule = Schedule.objects.filter(match=cls.match).first()
        if not cls.schedule:
            raise RuntimeError("Seeded schedule could not be found")
        cls.entry = ScheduleEntry.objects.filter(schedule=cls.schedule).first()
        if not cls.entry:
            raise RuntimeError("Seeded schedule entry could not be found")
        cls._setup_coordinator_invite()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.driver.quit()
        finally:
            cls._openai_override.disable()
            super().tearDownClass()

    def setUp(self):
        self.manifest = []
        for persona in ("careworker", "staff_admin", "client", "support_person"):
            (OUTPUT_DIR / persona).mkdir(parents=True, exist_ok=True)

    def _login(self, user):
        self.driver.delete_all_cookies()
        self.driver.get(f"{self.live_server_url}{reverse('login')}")
        username = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='username']"))
        )
        password = self.driver.find_element(By.CSS_SELECTOR, "input[name='password']")
        username.clear()
        username.send_keys(user.email)
        password.clear()
        password.send_keys(PASSWORD)
        self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        self.wait.until(lambda driver: "login" not in driver.current_url.lower())

    def _capture(self, persona, step, title, purpose, feature_summary, path):
        url = f"{self.live_server_url}{path}"
        self.driver.get(url)
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        # Query-string routes are how the matching page switches from its
        # transparent tag filter to the AI-assisted ranking view. Assert the
        # browser retained the requested mode so a redirect cannot silently
        # produce a mislabeled screenshot in the board package.
        if "ai=1" in path:
            self.wait.until(lambda driver: "AI-Assisted Matching" in driver.page_source)
        elif "tag_ids=" in path and "registry/network" in path:
            self.wait.until(lambda driver: "Matching " in driver.page_source)
        # Allow Django-rendered content and fonts to settle without introducing
        # a fragile element-specific wait for every page type.
        time.sleep(0.35)
        self._capture_current_page(
            persona, step, title, purpose, feature_summary, path
        )

    def _capture_current_page(
        self, persona, step, title, purpose, feature_summary, path, reset_scroll=True
    ):
        """Capture a complete page, using tiles only when it is exceptionally tall.

        Chrome's CDP Page.captureScreenshot supports a true full-page image and
        avoids the old viewport-only crop. For pages taller than the safe image
        limit, the fallback deliberately creates numbered, overlapping tiles.
        """
        if reset_scroll:
            self.driver.execute_script("window.scrollTo(0, 0)")
        dimensions = self.driver.execute_script(
            "return {width: Math.max(document.body.scrollWidth, document.documentElement.scrollWidth), "
            "height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)};"
        )
        page_height = max(int(dimensions["height"]), VIEWPORT_HEIGHT)
        page_width = max(int(dimensions["width"]), VIEWPORT_WIDTH)
        safe_title = _safe_filename(title)

        def append_manifest(filename, part_label=""):
            self.manifest.append({
                "persona": persona,
                "step": step,
                "title": title + (f" ({part_label})" if part_label else ""),
                "purpose": purpose,
                "feature_summary": feature_summary,
                "path": path,
                "screenshot": str(filename.relative_to(BASE_DIR)).replace("\\", "/"),
                "capture_mode": "full_page" if not part_label else "tiled",
                "page_height": page_height,
            })

        if page_height <= MAX_FULL_PAGE_HEIGHT:
            self.driver.set_window_size(page_width, VIEWPORT_HEIGHT)
            # CDP returns a PNG of the entire document, including content below
            # the viewport, without requiring the browser window to be enormous.
            result = self.driver.execute_cdp_cmd(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": True, "fromSurface": True},
            )
            import base64
            output = OUTPUT_DIR / persona / f"{step:02d}_{safe_title}.png"
            output.write_bytes(base64.b64decode(result["data"]))
            append_manifest(output)
            self.driver.set_window_size(VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
            return

        # Large rating histories are captured as overlapping viewport tiles so
        # no table row disappears and each PNG remains easy to view/share.
        tile_height = VIEWPORT_HEIGHT - 90
        overlap = 90
        top = 0
        tile_number = 1
        while top < page_height:
            self.driver.set_window_size(VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
            self.driver.execute_script("window.scrollTo(0, arguments[0])", top)
            time.sleep(0.15)
            output = OUTPUT_DIR / persona / f"{step:02d}_{safe_title}_part{tile_number}.png"
            self.driver.save_screenshot(str(output))
            append_manifest(output, f"part {tile_number}")
            if top + tile_height >= page_height:
                break
            top += tile_height - overlap
            tile_number += 1
        self.driver.execute_script("window.scrollTo(0, 0)")

    def _capture_after_click(
        self, persona, step, title, purpose, feature_summary, css_selector
    ):
        """Click a real control, wait for its response, and capture the result."""
        button = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector))
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", button
        )
        button.click()
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(0.35)
        self._capture_current_page(
            persona, step, title, purpose, feature_summary, self.driver.current_url
        )

    def _first_schedule_entry_url(self):
        return reverse("schedule_entry_rate", args=[self.entry.pk])

    def _tag_id(self):
        from matching.models import Tag
        # The seeded profiles are intentionally varied. Choose a tag shared by
        # the primary demo pair so both the tag filter and AI-ranking examples
        # contain a real candidate rather than two identical empty states.
        caregiver = self.match.caregiver
        client = self.match.client
        shared_keys = set(caregiver.experience_with or []) & set(client.care_needs or [])
        tag = Tag.objects.filter(
            is_active=True,
            name__in=[key.replace("_", "-") for key in shared_keys],
        ).order_by("pk").first()
        if not tag:
            raise RuntimeError("No active tag overlaps the seeded demonstration pair")
        return str(tag.pk)

    def _pair_match(self, pair_number):
        """Return the seeded pair's match, schedule, and first entry."""
        caregiver = get_user_model().objects.get(email=f"cilcg{pair_number}@example.com")
        client_user = get_user_model().objects.get(email=f"cilcl{pair_number}@example.com")
        match = Match.objects.filter(
            caregiver__user_profile__user=caregiver,
            client__user_profile__user=client_user,
        ).first()
        schedule = Schedule.objects.filter(match=match).first()
        entry = ScheduleEntry.objects.filter(schedule=schedule).first()
        return match, schedule, entry

    def _match_path(self, match):
        return reverse("match_stability_detail", args=[match.pk])

    def test_capture_all_journeys(self):
        """Capture all four persona journeys into the configured output folder."""
        # Shared introduction screens are captured once for each persona folder
        # so each journey can be presented independently.
        tag_id = self._tag_id()
        stable_match = self.match
        stable_schedule = self.schedule
        stable_entry = self.entry
        at_risk_match, _, _ = self._pair_match(3)

        journeys = [
            (
                "careworker",
                self.careworker,
                [
                    ("Apply as Careworker", "Join the careworker registry", "This public application form is where a person providing support begins. It collects the information needed for organizational review and later matching, without requiring an account first.", reverse("caregiver_apply")),
                    ("Home", "What CareWeb is", "The public landing page introduces CareWeb as a Personal Care Coordination and Stabilization workspace for people receiving support, careworkers, and organizations.", reverse("home")),
                    ("Login", "Secure role-based access", "The login screen is the entry point for role-specific dashboards. CareWeb uses the signed-in user's role and organization membership to show the appropriate tools.", reverse("login")),
                    ("Careworker Dashboard", "Personal work overview", "The careworker dashboard summarizes active relationships, schedules, pending actions, and links to the careworker's profile and matching tools.", reverse("caregiver_dashboard")),
                    ("Careworker Profile", "Skills and availability", "The profile presents the information used for compatibility: experience, location, availability, languages, transportation, preferences, and notes. The careworker can review and update these sections.", reverse("caregiver_profile")),
                    ("Tag Matching — Find Clients", "Filter possible clients by care criteria", "The careworker selects one or more care tags and uses Find Clients. Results show the relevant client, compatibility information, overlapping tags, and the option to request a match.", reverse("registry_network") + f"?tag_ids={tag_id}"),
                    ("AI Matching — Careworker", "AI-assisted client suggestions", "The AI Match action evaluates the careworker's profile and selected criteria to rank potential clients and explain the score. It supports the careworker's review and choice rather than automatically creating a relationship.", reverse("registry_network") + f"?tag_ids={tag_id}&ai=1"),
                    ("Schedule Detail", "Shared care plan", "The schedule detail page shows the client, careworker, organization, dates, recurring time slots, approvals, notes, and response status for the working relationship.", reverse("schedule_detail", args=[stable_schedule.pk])),
                    ("Rate Your Experience", "Ongoing relationship feedback", "After a session, the careworker can independently rate care fit, communication, reliability, and workload balance on a 1–10 scale. These ratings contribute to human-reviewed stability insights.", reverse("schedule_entry_rate", args=[stable_entry.pk])),
                ],
            ),
            (
                "staff_admin",
                self.admin,
                [
                    ("Login", "Secure staff access", "Staff sign in to access organization-level rosters, approvals, matching tools, schedules, and relationship-support indicators.", reverse("login")),
                    ("Organization Dashboard", "Organization-wide coordination", "The staff dashboard provides a consolidated view of participants, active matches, schedules, and Stability Snapshot status so staff can prioritize follow-up.", reverse("org_dashboard")),
                    ("Careworker Pool", "Review the careworker network", "The careworker pool lets staff review participating careworkers, their approval status, and profile information used for safe and relevant matching.", reverse("caregiver_pool")),
                    ("Client Pool", "Review people seeking support", "The client pool gives staff a separate view of client applications, review status, and profile links so the organization can coordinate participation and matching.", reverse("client_pool")),
                    ("Tag Matching — Staff", "Find matches using selected criteria", "Staff can choose a direction, select a careworker or client, apply tags, and use Find Matches. This is a transparent criteria-based workflow before considering AI assistance.", reverse("registry_network") + f"?match_type=find_clients&caregiver_id={self.match.caregiver.pk}&tag_ids={tag_id}"),
                    ("AI Matching — Staff", "Compare ranked pairings", "The staff AI matching page accepts optional careworker/client constraints and tags, then presents scores, matched tags, AI reasoning, and a human-controlled Propose Match action.", reverse("registry_network") + f"?match_type=find_clients&caregiver_id={self.match.caregiver.pk}&tag_ids={tag_id}&ai=1"),
                    ("Stability Snapshot — Stable", "Review a healthy consumer match", "This populated example shows the Green/Stable relationship state, overall score, five relationship signals, glossary definitions, and the underlying client/careworker session ratings.", self._match_path(stable_match)),
                    ("Stability Snapshot — At Risk", "Review a match needing attention", "This second seeded client/careworker match demonstrates the Red/At Risk state and shows how low or concerning rating patterns are made visible for staff support conversations.", self._match_path(at_risk_match)),
                    ("Flag for Stabilization Review", "Create a human follow-up signal", "Staff can flag the at-risk relationship directly from the real Stability Detail control. The resulting state records that review is requested and changes the Support Flags signal to Immediate review recommended.", self._match_path(at_risk_match)),
                ],
            ),
            (
                "client",
                self.client_user,
                [
                    ("Apply for Support", "Join the client registry", "This public application form is where a person looking for support begins. It collects care needs and personal context for organizational review and later matching.", reverse("client_apply")),
                    ("Home", "Understand the service", "The landing page explains the purpose of the Personal Care Coordination and Stabilization service and provides clear paths for people seeking support, careworkers, and organizations.", reverse("home")),
                    ("Login", "Client account access", "The client signs in to see their own care coordination workspace and information, separate from staff and careworker views.", reverse("login")),
                    ("Client Dashboard", "Manage support coordination", "The client dashboard summarizes matches, schedules, approvals, session information, and invitations for a support person.", reverse("client_dashboard")),
                    ("Client Profile", "Describe personal care preferences", "The client profile captures care needs, programs, availability, languages, scheduling preferences, and other context so matching can reflect the client's circumstances.", reverse("client_profile")),
                    ("Tag Matching — Find Careworkers", "Filter careworkers by care needs", "The client selects one or more care-needs tags and uses Find Careworkers. Results show potential careworkers, matched criteria, explanations, and a client-controlled Request Match action.", reverse("registry_network") + f"?tag_ids={tag_id}"),
                    ("AI Matching — Client", "AI-assisted careworker suggestions", "The AI Match action ranks careworkers against the client's needs, availability, and selected tags, and displays reasoning so the client can make an informed choice.", reverse("registry_network") + f"?tag_ids={tag_id}&ai=1"),
                    ("Schedule Detail", "Review the agreed schedule", "The client can review recurring time slots, approval state, participating careworker, notes, and session-level actions in one place.", reverse("schedule_detail", args=[stable_schedule.pk])),
                    ("Rate Your Experience", "Share the client's perspective", "The client uses the same independent rating categories to describe care fit, communication, reliability, and workload balance. Both perspectives help staff identify patterns without replacing human judgment.", reverse("schedule_entry_rate", args=[stable_entry.pk])),
                ],
            ),
        ]

        for persona, user, steps in journeys:
            if persona != "careworker" or True:
                # Apply pages and Home are intentionally captured logged out;
                # the helper below handles the role transition for the rest.
                pass
            self.driver.delete_all_cookies()
            for step, (title, purpose, feature_summary, path) in enumerate(steps, start=1):
                if title.startswith("Apply") or title == "Home":
                    self.driver.get(f"{self.live_server_url}{path}")
                    self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    time.sleep(0.25)
                    self._capture_current_page(persona, step, title, purpose, feature_summary, path)
                    continue
                if title == "Login":
                    self._login(user)
                    self._capture_current_page(persona, step, title, purpose, feature_summary, path)
                    continue
                # Re-authenticate after public screens and before the first
                # authenticated journey step.
                if "login" not in self.driver.current_url.lower() and not self.driver.get_cookie("sessionid"):
                    self._login(user)
                self._capture(persona, step, title, purpose, feature_summary, path)

            if persona == "staff_admin":
                # The last step is specifically an interaction: open the at-risk
                # detail page and submit the real flag form, then capture response.
                self._login(self.admin)
                flag_path = self._match_path(at_risk_match)
                self.driver.get(f"{self.live_server_url}{flag_path}")
                self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                self._capture_after_click(
                    persona, 10, "Flagged for Stabilization Review",
                    "Confirm human follow-up state",
                    "After staff submits the real flag action, the page confirms the relationship is flagged, identifies the request, and shows the updated Support Flags signal.",
                    f"form[action*='/stabilization-review/'] button[type='submit']",
                )

        # ── Support Person Journey ─────────────────────────────────────────────
        # Shows the invite-based onboarding path: client sends an invite, the
        # invitee accepts via the unique email link, creates an account, and
        # arrives at their own focused dashboard.
        if self.coordinator_invite:
            try:
                # Step 1: Client Dashboard — show the "Invite Support Person" button
                self._login(self.client_user)
                self._capture(
                    "support_person", 1,
                    "Client Dashboard — Invite Support Person",
                    "Client initiates the support-person invitation",
                    "The client dashboard shows the 'Invite a Support Person' button. Clicking it opens a simple form where the client enters the email address of the person they want to involve in their Personal Care Coordination and Stabilization.",
                    reverse("client_dashboard"),
                )

                # Step 2: Invite Support Person form
                self._capture(
                    "support_person", 2,
                    "Invite a Support Person",
                    "Client sends a secure email invitation",
                    "The client enters the support person's email address. The system sends a unique single-use link so the invitee can create an account and accept the role without a separate registration process.",
                    reverse("coordinator_invite_send"),
                )

                # Step 3: Coordinator Signup acceptance page (public invite link, no auth)
                self.driver.delete_all_cookies()
                signup_path = reverse("coordinator_signup", args=[self.coordinator_invite.token])
                self.driver.get(f"{self.live_server_url}{signup_path}")
                self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(0.4)
                self._capture_current_page(
                    "support_person", 3,
                    "Accept Support Person Invitation",
                    "Invitee creates their account via email link",
                    "The invited person arrives at this page from their unique email link. They fill in their name, set a password, provide a phone number, contact preferences, and describe their relationship to the client. On submit they are logged in automatically and directed to their dashboard.",
                    signup_path,
                )

                # Fill and submit the signup form to create the coordinator account
                self.driver.find_element(By.NAME, "first_name").send_keys("Demo")
                self.driver.find_element(By.NAME, "last_name").send_keys("Support")
                pw1 = self.driver.find_element(By.NAME, "password1")
                pw2 = self.driver.find_element(By.NAME, "password2")
                pw1.clear(); pw1.send_keys("DemoPass99!!")
                pw2.clear(); pw2.send_keys("DemoPass99!!")
                self.driver.find_element(By.NAME, "phone").send_keys("555-0199")
                checkboxes = self.driver.find_elements(
                    By.CSS_SELECTOR, "input[name='contact_preferences']"
                )
                if checkboxes:
                    checkboxes[0].click()
                self.driver.find_element(By.NAME, "relationship_to_clients").send_keys(
                    "Family member"
                )
                self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                # Wait for redirect to coordinator dashboard after auto-login
                self.wait.until(
                    lambda d: "coordinator/dashboard" in d.current_url
                    or "/dashboard" in d.current_url
                )
                time.sleep(0.5)

                # Step 4: Support Person Dashboard (auto-logged-in after signup)
                dashboard_path = reverse("coordinator_dashboard")
                self._capture_current_page(
                    "support_person", 4,
                    "Support Person Dashboard",
                    "Dedicated dashboard for the support person",
                    "After accepting the invitation, the support person lands on their dedicated dashboard. It lists the clients they support, their permissions (edit profile, approve careworkers), and any schedule entries awaiting their approval — keeping the support-person role focused and separate from staff or careworker views.",
                    dashboard_path,
                )
            except Exception as exc:
                print(f"\n  [support_person journey step failed: {exc}]")

        with open(OUTPUT_DIR / "manifest.json", "w", encoding="utf-8") as handle:
            json.dump(self.manifest, handle, indent=2)


if __name__ == "__main__":
    # Run only this artifact-producing test. Test discovery supplies the live
    # server and isolated DB; verbosity keeps the console useful.
    from django.core.management import execute_from_command_line

    sys.argv = [
        "manage.py",
        "test",
        "generate_screenshots.JourneyCapture.test_capture_all_journeys",
        "--settings=config.test_settings",
        "--verbosity=1",
    ]
    execute_from_command_line(sys.argv)
