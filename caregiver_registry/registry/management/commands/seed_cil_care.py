"""
Django management command to seed a complete CIL-Care demo environment.

Creates:
  - The CIL-Care organisation with a ready-to-use admin account.
  - N matched caregiver/client pairs (default 10), all approved members of
    CIL-Care, with active Matches, fully-approved Schedules + ScheduleEntries,
    and past ScheduleEntryRatings from both parties.

Usage:
    python manage.py seed_cil_care
    python manage.py seed_cil_care --count 5
    python manage.py seed_cil_care --clear

Credentials:
    Org admin  : cil-projects@thecil.org / carewebai2026
    Caregivers : cilcg1@example.com … cilcgN@example.com / carewebai2026
    Clients    : cilcl1@example.com … cilclN@example.com / carewebai2026
"""

import random
from datetime import date, timedelta, time as dtime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

# ── Constants ────────────────────────────────────────────────────────────────

SEED_PASSWORD = "carewebai2026"
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

EXPERIENCE_OPTIONS = [
    "domestic_tasks", "cooking", "bathing", "dressing", "errands",
    "lifting_transfers", "elders", "cognitive_disabilities",
    "chronic_illness", "lgbtq", "person_centered",
]

CARE_NEEDS_OPTIONS = [
    "domestic_tasks", "cooking", "bathing", "dressing", "errands",
    "lifting_transfers", "elders", "cognitive_disabilities",
    "chronic_illness", "lgbtq", "person_centered",
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
    """
    today = date.today()
    target_dow = _DAY_TO_INT[day_name]
    # Find the most recent past occurrence
    days_since = (today.weekday() - target_dow) % 7 or 7
    most_recent = today - timedelta(days=days_since)
    return [most_recent - timedelta(weeks=i) for i in range(weeks_back)]


# ── Main Command ──────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Seeds the CIL-Care demo organisation with matched caregiver/client pairs, "
        "approved schedules, and past ratings."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Number of caregiver/client matched pairs to create (default 10).",
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

        # 2. Matched pairs
        created_pairs = []
        for i in range(1, count + 1):
            cg_profile, cl_profile = self._create_matched_pair(i, org, admin_user_profile)
            created_pairs.append((cg_profile, cl_profile))
            self.stdout.write(f"  Pair {i:>2}: {cg_profile.user_profile.display_name}"
                              f" ↔ {cl_profile.user_profile.display_name}")

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Done!  Created {len(created_pairs)} matched pairs in '{ORG_NAME}'."
            f"\n\n  Org admin : {ORG_EMAIL} / {SEED_PASSWORD}"
            f"\n  Caregivers: cilcg1@example.com … cilcg{count}@example.com / {SEED_PASSWORD}"
            f"\n  Clients   : cilcl1@example.com … cilcl{count}@example.com / {SEED_PASSWORD}"
            f"\n\n  All pairs have:"
            f"\n    • Active matches (both parties approved)"
            f"\n    • Approved weekly schedules with 2–3 time slots"
            f"\n    • Past ratings (5 weeks of history) from both client & caregiver\n"
        ))

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

        # Ratings and schedules cascade from entries/schedules, but let's be explicit.
        # Matches in this org
        match_count, _ = Match.objects.filter(organization=org).delete()

        # Schedule ratings for this org's schedules
        rating_count, _ = ScheduleEntryRating.objects.filter(
            schedule_entry__schedule__organization=org
        ).delete()

        # Schedules / entries cascade
        sched_count, _ = Schedule.objects.filter(organization=org).delete()

        # Caregiver/client relationships
        cg_rels = OrganizationCaregiver.objects.filter(organization=org)
        cg_profiles = list(cg_rels.values_list("caregiver_profile_id", flat=True))
        cl_rels = OrganizationClient.objects.filter(organization=org)
        cl_profiles = list(cl_rels.values_list("client_profile_id", flat=True))

        cg_rels.delete()
        cl_rels.delete()

        # Delete caregiver/client profiles + users for the seeded email pattern only
        for cg in CaregiverProfile.objects.filter(pk__in=cg_profiles):
            user = cg.user_profile.user
            if "cilcg" in user.email:
                user.delete()  # cascades to UserProfile → CaregiverProfile

        for cl in ClientProfile.objects.filter(pk__in=cl_profiles):
            user = cl.user_profile.user
            if "cilcl" in user.email:
                user.delete()

        self.stdout.write(self.style.WARNING(
            f"  Cleared: {match_count} matches, {sched_count} schedules, "
            f"{rating_count} ratings and associated profiles."
        ))

    # ── Pair creation ─────────────────────────────────────────────────────────

    def _create_matched_pair(self, index, org, admin_profile):
        """
        Create one caregiver + one client, approved in org, with an active
        Match, an approved Schedule, and past ScheduleEntryRatings.
        """
        cg_profile = self._create_caregiver(index)
        cl_profile  = self._create_client(index)

        self._link_caregiver_to_org(cg_profile, org, admin_profile)
        self._link_client_to_org(cl_profile, org, admin_profile)

        match = self._create_active_match(cg_profile, cl_profile, org, admin_profile)
        schedule = self._create_approved_schedule(cg_profile, cl_profile, org, match, admin_profile)
        self._create_ratings(schedule, cg_profile, cl_profile)

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

        # Ensure meaningful skill overlap with the paired client
        experience = random.sample(EXPERIENCE_OPTIONS, k=random.randint(4, 7))

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

    def _create_client(self, index):
        from accounts.models import UserProfile
        from registry.models import ClientProfile

        email = f"cilcl{index}@example.com"
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
                "address": f"{random.randint(100, 9999)} Oak St, Oakland, CA {ORG_ZIP}",
            },
        )

        # Overlap with caregivers experience pool
        care_needs = random.sample(CARE_NEEDS_OPTIONS, k=random.randint(3, 6))

        profile, _ = ClientProfile.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                "base_zip_code": ORG_ZIP,
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

        # Check for existing match first
        existing = Match.objects.filter(
            organization=org, caregiver=cg_profile, client=cl_profile
        ).first()
        if existing:
            return existing

        # Compute a real local score for realism
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

        # Start date is ~6 weeks ago so ratings can cover 5 past weeks
        start_date = date.today() - timedelta(weeks=6)

        # Check for existing approved schedule for this match
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

        # Pick 2–3 unique time slots
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

    def _create_ratings(self, schedule, cg_profile, cl_profile):
        from registry.models import ScheduleEntry, ScheduleEntryRating

        client_up    = cl_profile.user_profile
        caregiver_up = cg_profile.user_profile

        for entry in ScheduleEntry.objects.filter(schedule=schedule):
            occurrences = _past_occurrences(entry.day_of_week, weeks_back=5)

            for occurrence_date in occurrences:
                for rater_up, rater_role in [
                    (client_up,    "client"),
                    (caregiver_up, "caregiver"),
                ]:
                    # Plausible-but-varied scores, skewed positive (6–10)
                    scores = {
                        "care_fit_respect":          random.randint(6, 10),
                        "communication_coordination": random.randint(6, 10),
                        "reliability_consistency":    random.randint(6, 10),
                        "workload_support_balance":   random.randint(5, 10),
                    }
                    notes_pool = [
                        "",
                        "Great session overall.",
                        "Some scheduling adjustments needed.",
                        "Communication was excellent this visit.",
                        "Looking forward to continuing this relationship.",
                        "Minor timing issues but resolved quickly.",
                        "Very professional and attentive.",
                    ]

                    ScheduleEntryRating.objects.get_or_create(
                        schedule_entry=entry,
                        rater_profile=rater_up,
                        rating_date=occurrence_date,
                        defaults={
                            "rater_role": rater_role,
                            "notes": random.choice(notes_pool),
                            **scores,
                        },
                    )
