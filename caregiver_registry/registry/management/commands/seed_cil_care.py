"""
Django management command to seed a complete CIL-Care demo environment.

Creates:
  - The CIL-Care organisation with a ready-to-use admin account.
  - N matched caregiver/client pairs (default 9, one per rating scenario),
    all approved members of CIL-Care, with active Matches, fully-approved
    Schedules + ScheduleEntries, and contrasting past ScheduleEntryRatings
    that exercise every Stability Snapshot status and signal combination.

Rating scenarios (cycling when --count > 9):
  1 — Green  / Stable         : flat 9s — baseline high / all signals positive
  2 — Yellow / Monitor        : flat 6s — baseline mid
  3 — Red    / At Risk        : flat 3s — baseline low
  4 — Declining trend         : starts 9 (oldest) → drops to 3 (newest)
  5 — Improving trend         : starts 3 (oldest) → rises to 9 (newest)
  6 — Volatile / inconsistent : alternates 9, 3, 9, 3, 9 week to week
  7 — Split perspective       : client rates ~9, caregiver rates ~3
  8 — Single-metric failure   : workload low (2–3), all others high (8–9)
  9 — No ratings yet          : schedule exists but zero ratings → "Not Yet Rated" badge

ZIP / travel-burden variation:
  Pairs 1–3 share org ZIP (94612) → travel_burden = Low
  Pair 4 uses client ZIP 94702 (Berkeley ~5 mi)  → travel_burden = Low/Moderate
  Pair 5 uses client ZIP 95112 (San Jose ~40 mi) → travel_burden = High
  Pair 6 uses client ZIP 94010 (Burlingame ~35 mi) → travel_burden = High
  Pairs 7–9 share org ZIP → travel_burden = Low

Usage:
    python manage.py seed_cil_care
    python manage.py seed_cil_care --count 9
    python manage.py seed_cil_care --clear

Credentials:
    Org admin  : cil-projects@thecil.org / cil-projects@thecil.org
    Caregivers : cilcg1@example.com … cilcgN@example.com / cil-projects@thecil.org
    Clients    : cilcl1@example.com … cilclN@example.com / cil-projects@thecil.org
"""

import random
from datetime import date, timedelta, time as dtime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

# ── Constants ────────────────────────────────────────────────────────────────

SEED_PASSWORD = "cil-projects@thecil.org"
ORG_NAME      = "CIL-Care"
ORG_EMAIL     = "cil-projects@thecil.org"
ORG_CITY      = "Oakland"
ORG_ZIP       = "94612"

FIRST_NAMES = [
    "James", "Michael", "David", "Daniel", "Anthony", "Christopher",
    "Matthew", "Joshua", "Andrew", "Joseph", "Robert", "William",
    "John", "Brian", "Kevin", "Jason", "Eric", "Steven", "Mark", "Ryan",
    "Sarah", "Jessica", "Ashley", "Amanda", "Brittany", "Emily",
    "Samantha", "Rachel", "Nicole", "Lauren", "Jennifer", "Elizabeth",
    "Michelle", "Stephanie", "Melissa", "Rebecca", "Heather", "Amber",
    "Danielle", "Christina", "Megan", "Kimberly", "Tiffany", "Angela",
    "Courtney", "Vanessa", "Erica", "Alyssa", "Monica", "Jasmine",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
]

# Full 33-key pools (mirrors registry.models.EXPERIENCE_CHOICES /
# CARE_NEEDS_CHOICES) so seeded caregiver/client overlap is a matter of
# chance rather than near-guaranteed. Keeping these in sync with the model
# choice lists avoids importing registry.models at module load time
# (management commands are imported before Django apps are fully ready).
EXPERIENCE_OPTIONS = [
    "domestic_tasks", "errands", "bathing", "cooking", "dressing",
    "assistive_technology", "bowel_programs", "couple_family", "catheters",
    "chair_users", "chronic_illness", "cna", "cognitive_disabilities",
    "complex_illnesses", "cpr", "deaf_community", "dementia",
    "developmental_disabilities", "elders", "emergency_preparedness", "emt",
    "cil_courses", "feeding_tubes", "fragrance_free", "anti_bias",
    "soft_skills", "hoyer_lifts", "ihss", "lgbtq", "lifting_transfers",
    "limited_english", "person_centered", "spinal_cord", "ventilators",
    "visual_impairments",
]

CARE_NEEDS_OPTIONS = [
    "domestic_tasks", "errands", "bathing", "cooking", "dressing",
    "assistive_technology", "bowel_programs", "couple_family", "catheters",
    "chair_users", "chronic_illness", "cognitive_disabilities",
    "complex_illnesses", "deaf_community", "dementia",
    "developmental_disabilities", "elders", "emergency_preparedness",
    "feeding_tubes", "fragrance_free", "hoyer_lifts", "ihss", "lgbtq",
    "lifting_transfers", "limited_english", "person_centered",
    "spinal_cord", "ventilators", "visual_impairments",
]


DAYS_OF_WEEK = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

PERIODS = ["morning", "afternoon", "evening", "overnight"]

# Fixed weekly slots available for schedule entries
SLOT_OPTIONS = [
    ("monday",    dtime(8, 0),  dtime(12, 0)),
    ("monday",    dtime(13, 0), dtime(17, 0)),
    ("tuesday",   dtime(8, 0),  dtime(12, 0)),
    ("tuesday",   dtime(13, 0), dtime(17, 0)),
    ("wednesday", dtime(9, 0),  dtime(13, 0)),
    ("wednesday", dtime(14, 0), dtime(18, 0)),
    ("thursday",  dtime(8, 0),  dtime(12, 0)),
    ("thursday",  dtime(13, 0), dtime(17, 0)),
    ("friday",    dtime(9, 0),  dtime(13, 0)),
    ("friday",    dtime(14, 0), dtime(18, 0)),
    ("saturday",  dtime(10, 0), dtime(14, 0)),
    ("sunday",    dtime(10, 0), dtime(14, 0)),
]

# Day-name → integer (Mon=0) for date arithmetic
_DAY_TO_INT = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# ── Rating Scenarios ─────────────────────────────────────────────────────────
#
# Each scenario is a dict:
#   name        : display label
#   type        : 'flat' | 'trend' | 'volatile' | 'split' | 'single_metric' | 'none'
#   stability   : expected Stability Snapshot status for the console summary
#
# Additional keys vary by type (see _create_ratings for interpretation).

RATING_SCENARIOS = [
    # 1 — Green baseline
    {
        "name": "Green / Stable",
        "type": "flat",
        "stability": "green",
        "lo": 9, "hi": 9,
        "client_zip": ORG_ZIP,
    },
    # 2 — Yellow baseline
    {
        "name": "Yellow / Monitor",
        "type": "flat",
        "stability": "yellow",
        "lo": 6, "hi": 6,
        "client_zip": ORG_ZIP,
    },
    # 3 — Red baseline
    {
        "name": "Red / At Risk",
        "type": "flat",
        "stability": "red",
        "lo": 3, "hi": 3,
        "client_zip": ORG_ZIP,
    },
    # 4 — Declining trend (starts well → deteriorates)
    {
        "name": "Declining trend",
        "type": "trend",
        "stability": "yellow→red",
        "start": 9, "end": 3,   # oldest week = start, most recent week = end
        "client_zip": "94702",  # Berkeley ~5 mi → travel_burden = Low/Moderate
    },
    # 5 — Improving trend (rocky start → recovering)
    {
        "name": "Improving trend",
        "type": "trend",
        "stability": "red→green",
        "start": 3, "end": 9,
        "client_zip": "95112",  # San Jose ~40 mi → travel_burden = High
    },
    # 6 — Volatile / erratic week-to-week
    {
        "name": "Volatile / inconsistent",
        "type": "volatile",
        "stability": "yellow",
        "pattern": [9, 3, 9, 3, 9],   # values per week oldest→newest
        "client_zip": "94010",  # Burlingame ~35 mi → travel_burden = High
    },
    # 7 — Split perspective (client praises, caregiver struggles)
    {
        "name": "Split perspective (client high, caregiver low)",
        "type": "split",
        "stability": "yellow",
        "client_lo": 8, "client_hi": 9,
        "caregiver_lo": 2, "caregiver_hi": 4,
        "client_zip": ORG_ZIP,
    },
    # 8 — Single-metric failure (workload overload; all other metrics fine)
    {
        "name": "Single-metric failure (workload)",
        "type": "single_metric",
        "stability": "yellow→red",
        # workload_support_balance intentionally low; others stay high
        "default_lo": 8, "default_hi": 9,
        "override_metric": "workload_support_balance",
        "override_lo": 2, "override_hi": 3,
        "client_zip": ORG_ZIP,
    },
    # 9 — No ratings at all → "Not Yet Rated" (stability is never inferred from match_score)
    {
        "name": "No ratings yet (Not Yet Rated)",
        "type": "none",
        "stability": "none (Not Yet Rated)",
        "client_zip": ORG_ZIP,
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_availability():
    """Return a {day: [periods]} dict with 2–5 random days."""
    num_days = random.randint(2, 5)
    result = {}
    for day in random.sample(DAYS_OF_WEEK, num_days):
        result[day] = random.sample(PERIODS, k=random.randint(1, 3))
    return result


def _past_occurrences(day_name: str, weeks_back: int = 5) -> list:
    """
    Return the dates of the most recent `weeks_back` weekly occurrences of
    `day_name` that are strictly in the past (relative to today).
    Returns them oldest-first (index 0 = oldest, index -1 = most recent).
    """
    today = date.today()
    target_dow = _DAY_TO_INT[day_name]
    days_since = (today.weekday() - target_dow) % 7 or 7
    most_recent = today - timedelta(days=days_since)
    # reversed so index 0 = oldest
    return list(reversed([most_recent - timedelta(weeks=i) for i in range(weeks_back)]))


# Notes pools keyed by approximate rating quality
_NOTES_POSITIVE = [
    "",
    "Great session overall.",
    "Communication was excellent this visit.",
    "Very professional and attentive.",
    "Looking forward to continuing this relationship.",
]

_NOTES_NEUTRAL = [
    "",
    "Some scheduling adjustments needed.",
    "Minor timing issues but resolved quickly.",
    "Session was okay, a few things to follow up on.",
    "Things are progressing, could use a check-in.",
]

_NOTES_NEGATIVE = [
    "Significant concerns this session.",
    "Scheduling has been very difficult.",
    "Communication breakdown — needs immediate attention.",
    "Workload expectations are not being met.",
    "Requested a staff check-in.",
]


def _notes_for_score(avg_score):
    if avg_score >= 7:
        return random.choice(_NOTES_POSITIVE)
    elif avg_score >= 5:
        return random.choice(_NOTES_NEUTRAL)
    else:
        return random.choice(_NOTES_NEGATIVE)


# ── Main Command ──────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Seeds the CIL-Care demo organisation with matched caregiver/client pairs "
        "using 9 contrasting rating scenarios that exercise every Stability Snapshot "
        "status and signal combination."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=9,
            help=(
                "Number of caregiver/client matched pairs to create (default 9 — "
                "one per rating scenario). Values > 9 cycle back through the scenarios."
            ),
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help=(
                "Remove previously seeded CIL-Care caregivers, clients, matches, "
                "schedules and ratings before re-seeding. "
                "The org and admin account are preserved."
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        count = options["count"]
        do_clear = options["clear"]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== seed_cil_care : {ORG_NAME} ===\n"
        ))

        # 1. Organisation + admin
        org, admin_user_profile = self._get_or_create_org()

        if do_clear:
            self._clear_seeded_data(org)

        # 2. Matched pairs — cycle through RATING_SCENARIOS
        created_pairs = []
        for i in range(1, count + 1):
            scenario = RATING_SCENARIOS[(i - 1) % len(RATING_SCENARIOS)]
            cg_profile, cl_profile = self._create_matched_pair(
                i, org, admin_user_profile, scenario=scenario
            )
            created_pairs.append((cg_profile, cl_profile))
            self.stdout.write(
                f"  Pair {i:>2}: {cg_profile.user_profile.display_name}"
                f" ↔ {cl_profile.user_profile.display_name}"
                f"  [{scenario['name']}]"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Done!  Created {len(created_pairs)} matched pairs in '{ORG_NAME}'."
            f"\n\n  Org admin : {ORG_EMAIL} / {SEED_PASSWORD}"
            f"\n  Caregivers: cilcg1@example.com … cilcg{count}@example.com / {SEED_PASSWORD}"
            f"\n  Clients   : cilcl1@example.com … cilcl{count}@example.com / {SEED_PASSWORD}"
            f"\n\n  Rating scenarios applied (cycling):"
        ))
        for idx, sc in enumerate(RATING_SCENARIOS, 1):
            self.stdout.write(
                f"    {idx}. {sc['name']}"
                f"  [ZIP: {sc['client_zip']}]"
                f"  → expected stability: {sc['stability']}"
            )
        self.stdout.write("")

    # ── Organisation ─────────────────────────────────────────────────────────

    def _get_or_create_org(self):
        """
        Idempotently create the CIL-Care org and its admin account.
        Returns (org, admin_user_profile).
        """
        from accounts.models import UserProfile, StaffProfile
        from organizations.models import Organization, OrganizationStaff

        # Admin user
        admin_user, created = User.objects.get_or_create(
            email=ORG_EMAIL,
            defaults={
                "username": ORG_EMAIL,
                "first_name": random.choice(FIRST_NAMES),
                "last_name": "Admin",
                "is_active": True,
            },
        )
        if created or not admin_user.has_usable_password():
            admin_user.set_password(SEED_PASSWORD)
            admin_user.save()

        admin_profile, _ = UserProfile.objects.get_or_create(user=admin_user)
        staff_profile, _ = StaffProfile.objects.get_or_create(
            user_profile=admin_profile,
            defaults={"title": "Administrator"},
        )

        # Organisation
        org, org_created = Organization.objects.get_or_create(
            name=ORG_NAME,
            defaults={
                "city": ORG_CITY,
                "zip_code": ORG_ZIP,
                "contact_email": ORG_EMAIL,
                "primary_admin": staff_profile,
            },
        )

        # OrganizationStaff link
        OrganizationStaff.objects.get_or_create(
            organization=org,
            staff_profile=staff_profile,
            defaults={
                "role": "admin",
                "status": "active",
                "can_view_dashboard": True,
                "can_approve_applications": True,
                "can_invite_staff": True,
                "accepted_at": timezone.now(),
                "start_date": timezone.now().date(),
            },
        )

        action = "Created" if org_created else "Found existing"
        self.stdout.write(f"{action} organisation: {ORG_NAME}")
        return org, admin_profile

    # ── Clear ─────────────────────────────────────────────────────────────────

    def _clear_seeded_data(self, org):
        """Remove previously seeded CIL-Care demo data (keeps org + admin)."""
        from registry.models import (
            OrganizationCaregiver, OrganizationClient,
            Schedule, ScheduleEntry, ScheduleEntryRating, CaregiverProfile,
            ClientProfile,
        )
        from matching.models import Match

        match_count, _ = Match.objects.filter(organization=org).delete()

        rating_count, _ = ScheduleEntryRating.objects.filter(
            schedule_entry__schedule__organization=org
        ).delete()

        sched_count, _ = Schedule.objects.filter(organization=org).delete()

        cg_rels = OrganizationCaregiver.objects.filter(organization=org)
        cg_profiles = list(cg_rels.values_list("caregiver_profile_id", flat=True))
        cl_rels = OrganizationClient.objects.filter(organization=org)
        cl_profiles = list(cl_rels.values_list("client_profile_id", flat=True))

        cg_rels.delete()
        cl_rels.delete()

        for cg in CaregiverProfile.objects.filter(pk__in=cg_profiles):
            user = cg.user_profile.user
            if "cilcg" in user.email:
                user.delete()

        for cl in ClientProfile.objects.filter(pk__in=cl_profiles):
            user = cl.user_profile.user
            if "cilcl" in user.email:
                user.delete()

        self.stdout.write(self.style.WARNING(
            f"  Cleared: {match_count} matches, {sched_count} schedules, "
            f"{rating_count} ratings and associated profiles."
        ))

    # ── Pair creation ─────────────────────────────────────────────────────────

    def _create_matched_pair(self, index, org, admin_profile, scenario):
        """
        Create one caregiver + one client, approved in org, with an active
        Match, an approved Schedule, and past ScheduleEntryRatings per scenario.

        The client ZIP is taken from scenario["client_zip"] so travel_burden
        varies across scenario types.
        """
        client_zip = scenario.get("client_zip", ORG_ZIP)
        cg_profile = self._create_caregiver(index)
        cl_profile  = self._create_client(index, client_zip=client_zip)

        self._link_caregiver_to_org(cg_profile, org, admin_profile)
        self._link_client_to_org(cl_profile, org, admin_profile)

        match = self._create_active_match(cg_profile, cl_profile, org, admin_profile)
        schedule = self._create_approved_schedule(cg_profile, cl_profile, org, match, admin_profile)

        # Scenario 9 ("none") intentionally skips rating creation
        if scenario["type"] != "none":
            self._create_ratings(schedule, cg_profile, cl_profile, scenario=scenario)

        return cg_profile, cl_profile

    # ── Caregiver ────────────────────────────────────────────────────────────

    def _create_caregiver(self, index):
        from accounts.models import UserProfile
        from registry.models import CaregiverProfile

        email = f"cilcg{index}@example.com"
        first = random.choice(FIRST_NAMES)
        last  = random.choice(LAST_NAMES)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": first,
                "last_name": last,
                "is_active": True,
            },
        )
        if created:
            user.set_password(SEED_PASSWORD)
            user.save()

        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "phone": f"555-{random.randint(100,999)}-{random.randint(1000,9999)}",
                "pronouns": random.choice(["she_her", "he_him", "they_them", ""]),
                "contact_preferences": random.sample(
                    ["phone", "email", "text"], k=random.randint(1, 2)
                ),
            },
        )

        experience = random.sample(EXPERIENCE_OPTIONS, k=random.randint(3, 5))


        profile, _ = CaregiverProfile.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                "base_zip_code": ORG_ZIP,
                "willing_to_work_cities": ["Oakland", "Berkeley"],
                "transportation": random.sample(
                    ["licensed_driver", "vehicle_access", "insured"],
                    k=random.randint(1, 3),
                ),
                "availability": _generate_availability(),
                "hours_looking_for": random.choice(["part_time", "full_time", "flexible"]),
                "desired_hours_per_week": random.choice([20, 25, 30, 40]),
                "certified_ihss_worker": random.choice([True, False]),
                "additional_certifications": random.choice(
                    ["", "CPR Certified", "First Aid", "CNA License"]
                ),
                "experience_with": experience,
                "languages_spoken": random.sample(["english", "spanish"], k=random.randint(1, 2)),
                "pathogen_protocols": random.sample(
                    ["n95_at_work", "masking_indoors"], k=random.randint(0, 2)
                ),
                "rate": random.choice(["17_20", "20_25", "25_30", "30_50"]),
                "bio": (
                    f"Dedicated careworker with {random.randint(2, 10)} years of experience "
                    "supporting individuals in Oakland and the Bay Area."
                ),
                "wants_training_updates": random.choice([True, False]),
            },
        )
        return profile

    # ── Client ───────────────────────────────────────────────────────────────

    def _create_client(self, index, client_zip=None):
        from accounts.models import UserProfile
        from registry.models import ClientProfile

        email = f"cilcl{index}@example.com"
        first = random.choice(FIRST_NAMES)
        last  = random.choice(LAST_NAMES)
        zip_code = client_zip or ORG_ZIP

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": first,
                "last_name": last,
                "is_active": True,
            },
        )
        if created:
            user.set_password(SEED_PASSWORD)
            user.save()

        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "phone": f"555-{random.randint(100,999)}-{random.randint(1000,9999)}",
                "pronouns": random.choice(["she_her", "he_him", "they_them", ""]),
                "contact_preferences": random.sample(
                    ["phone", "email", "text"], k=random.randint(1, 2)
                ),
                "address": f"{random.randint(100, 9999)} Oak St, Oakland, CA {zip_code}",
            },
        )

        care_needs = random.sample(CARE_NEEDS_OPTIONS, k=random.randint(3, 5))


        profile, _ = ClientProfile.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                "base_zip_code": zip_code,
                "attendant_care_programs": random.sample(
                    ["ihss", "wpcs", "out_of_pocket"], k=random.randint(1, 2)
                ),
                "languages_preferred": random.sample(
                    ["english", "spanish"], k=random.randint(1, 2)
                ),
                "availability": _generate_availability(),
                "schedule_flexibility": True,
                "hours_per_week": random.choice([20, 25, 30, 40]),
                "care_needs": care_needs,
                "additional_care_needs": random.choice(
                    [
                        "",
                        "Assistance with medications",
                        "Transportation to appointments",
                        "Help with meal planning",
                    ]
                ),
                "pathogen_protocol_preferences": random.sample(
                    ["n95_at_work", "masking_indoors"], k=random.randint(0, 2)
                ),
            },
        )
        return profile

    # ── Org Membership ───────────────────────────────────────────────────────

    def _link_caregiver_to_org(self, cg_profile, org, admin_profile):
        from registry.models import OrganizationCaregiver

        OrganizationCaregiver.objects.get_or_create(
            organization=org,
            caregiver_profile=cg_profile,
            defaults={
                "status": "approved",
                "approved_by": admin_profile,
                "approved_at": timezone.now(),
            },
        )

    def _link_client_to_org(self, cl_profile, org, admin_profile):
        from registry.models import OrganizationClient

        OrganizationClient.objects.get_or_create(
            organization=org,
            client_profile=cl_profile,
            defaults={
                "status": "approved",
                "approved_by": admin_profile,
                "approved_at": timezone.now(),
            },
        )

    # ── Match ─────────────────────────────────────────────────────────────────

    def _create_active_match(self, cg_profile, cl_profile, org, admin_profile):
        from matching.models import Match
        from matching.services import compute_match_score

        existing = Match.objects.filter(
            organization=org, caregiver=cg_profile, client=cl_profile
        ).first()
        if existing:
            return existing

        score_result = compute_match_score(cg_profile, cl_profile)

        match = Match.objects.create(
            organization=org,
            caregiver=cg_profile,
            client=cl_profile,
            initiated_by="staff",
            initiated_by_user=admin_profile,
            caregiver_status="approved",
            client_status="approved",
            staff_status="approved",
            status="active",
            match_score=score_result["score"],
            match_details=score_result["details"],
            ai_reasoning=score_result["ai_reasoning"],
            notes="Seeded demo match — CIL-Care.",
        )
        return match

    # ── Schedule ─────────────────────────────────────────────────────────────

    def _create_approved_schedule(self, cg_profile, cl_profile, org, match, admin_profile):
        from registry.models import Schedule, ScheduleEntry

        start_date = date.today() - timedelta(weeks=6)

        existing = Schedule.objects.filter(
            organization=org,
            caregiver=cg_profile,
            client=cl_profile,
            status="approved",
        ).first()
        if existing:
            return existing

        schedule = Schedule.objects.create(
            organization=org,
            client=cl_profile,
            caregiver=cg_profile,
            match=match,
            created_by=cl_profile.user_profile,
            support_person=None,
            status="approved",
            start_date=start_date,
            frequency="weekly",
            notes="Seeded demo schedule — CIL-Care.",
            submitted_at=timezone.now() - timedelta(weeks=6),
        )

        chosen_slots = random.sample(SLOT_OPTIONS, k=random.randint(2, 3))
        for day, start_t, end_t in chosen_slots:
            ScheduleEntry.objects.get_or_create(
                schedule=schedule,
                day_of_week=day,
                start_time=start_t,
                end_time=end_t,
                defaults={
                    "caregiver_status": "approved",
                    "caregiver_reviewed_at": timezone.now() - timedelta(weeks=5),
                    "support_person_status": "approved",
                    "support_person_reviewed_at": timezone.now() - timedelta(weeks=5),
                },
            )

        return schedule

    # ── Ratings ───────────────────────────────────────────────────────────────

    def _create_ratings(self, schedule, cg_profile, cl_profile, scenario):
        """
        Create ScheduleEntryRating rows for all entries in `schedule` using
        the given scenario definition.

        Scenario types:
          flat          — all metrics clamped to randint(lo, hi) for all raters/weeks
          trend         — score interpolates linearly from `start` to `end` over 5 weeks
                          (oldest week = start value, most recent week = end value)
          volatile      — per-week values follow `pattern` list (oldest→newest);
                          all metrics = pattern[week_idx]
          split         — client uses (client_lo, client_hi); caregiver uses (caregiver_lo, caregiver_hi)
          single_metric — all metrics use (default_lo, default_hi) except `override_metric`
                          which uses (override_lo, override_hi)
        """
        from registry.models import ScheduleEntry, ScheduleEntryRating

        client_up    = cl_profile.user_profile
        caregiver_up = cg_profile.user_profile
        stype        = scenario["type"]

        for entry in ScheduleEntry.objects.filter(schedule=schedule):
            # oldest-first list of past occurrence dates
            occurrences = _past_occurrences(entry.day_of_week, weeks_back=5)

            for week_idx, occurrence_date in enumerate(occurrences):
                # ── compute per-week base value ─────────────────────────────
                if stype == "flat":
                    week_value = (scenario["lo"], scenario["hi"])

                elif stype == "trend":
                    # linear interpolation from start → end over 5 steps
                    start_v = scenario["start"]
                    end_v   = scenario["end"]
                    steps   = max(len(occurrences) - 1, 1)
                    v = round(start_v + (end_v - start_v) * week_idx / steps)
                    v = max(1, min(10, v))
                    week_value = (v, v)

                elif stype == "volatile":
                    pattern = scenario["pattern"]
                    v = pattern[week_idx % len(pattern)]
                    week_value = (v, v)

                elif stype in ("split", "single_metric"):
                    week_value = None  # handled per-rater below

                else:
                    week_value = (6, 8)  # safe fallback

                # ── create one rating per rater ─────────────────────────────
                for rater_up, rater_role in [
                    (client_up,    "client"),
                    (caregiver_up, "caregiver"),
                ]:
                    # ── build scores dict ───────────────────────────────────
                    if stype == "split":
                        if rater_role == "client":
                            lo, hi = scenario["client_lo"], scenario["client_hi"]
                        else:
                            lo, hi = scenario["caregiver_lo"], scenario["caregiver_hi"]
                        scores = {
                            "care_fit_respect":           random.randint(lo, hi),
                            "communication_coordination": random.randint(lo, hi),
                            "reliability_consistency":    random.randint(lo, hi),
                            "workload_support_balance":   random.randint(lo, hi),
                        }

                    elif stype == "single_metric":
                        d_lo = scenario["default_lo"]
                        d_hi = scenario["default_hi"]
                        o_metric = scenario["override_metric"]
                        o_lo = scenario["override_lo"]
                        o_hi = scenario["override_hi"]
                        scores = {
                            "care_fit_respect":           random.randint(d_lo, d_hi),
                            "communication_coordination": random.randint(d_lo, d_hi),
                            "reliability_consistency":    random.randint(d_lo, d_hi),
                            "workload_support_balance":   random.randint(d_lo, d_hi),
                        }
                        scores[o_metric] = random.randint(o_lo, o_hi)

                    else:
                        lo, hi = week_value
                        scores = {
                            "care_fit_respect":           random.randint(lo, hi),
                            "communication_coordination": random.randint(lo, hi),
                            "reliability_consistency":    random.randint(lo, hi),
                            "workload_support_balance":   random.randint(lo, hi),
                        }

                    # ── sentiment-appropriate notes ─────────────────────────
                    avg_score = sum(scores.values()) / len(scores)
                    notes_text = _notes_for_score(avg_score)

                    ScheduleEntryRating.objects.get_or_create(
                        schedule_entry=entry,
                        rater_profile=rater_up,
                        rating_date=occurrence_date,
                        defaults={
                            "rater_role": rater_role,
                            "notes": notes_text,
                            **scores,
                        },
                    )
