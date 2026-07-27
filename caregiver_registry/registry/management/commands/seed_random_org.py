"""
Django management command to seed (or re-seed) an arbitrary test organization
with randomized caregiver/client members, designed to produce a realistic
*spread* of AI/local match scores instead of clustering everyone into a
narrow high-score band.

Unlike seed_cil_care.py (which intentionally clusters ZIPs/tags to exercise
specific Stability Snapshot rating scenarios), this command spreads caregiver
and client ZIP codes across a wide range of real Bay Area / California
locations and draws skills/needs from the full 33-key choice pools, so
location score and tag-overlap score both vary naturally across the full
range (0-10 pts and 0-40 pts respectively).

No schedules, matches, or ratings are created — this command only produces
approved org members ready for on-demand AI-assisted / tag-based matching
testing via the Network Registry UI.

Usage:
    python manage.py seed_random_org --org-name "CareHouse94521"
    python manage.py seed_random_org --org-name "CareHouse94521" --caregivers 8 --clients 8
    python manage.py seed_random_org --org-name "CareHouse94521" --clear
"""

import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

User = get_user_model()

# ── Constants ────────────────────────────────────────────────────────────────

SEED_PASSWORD = "carewebai2026"

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

# Full 33-key pools mirroring registry.models.EXPERIENCE_CHOICES /
# CARE_NEEDS_CHOICES keys.
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

# Themed "specialty" clusters used to generate more realistic tag overlap.
# Each caregiver/client is assigned a random specialty theme and draws most
# of their tags from that theme's cluster (plus a couple of random extras).
# This produces a natural bimodal spread: pairs sharing a specialty tend to
# score well on tag overlap, while cross-specialty pairs score low — instead
# of every pair drawing uniformly at random from all 33 tags (which pushes
# nearly all overlap scores toward the low end).
SPECIALTY_CLUSTERS = {
    "mobility": [
        "lifting_transfers", "chair_users", "hoyer_lifts", "catheters",
        "feeding_tubes", "bowel_programs", "spinal_cord", "ventilators",
    ],
    "cognitive": [
        "dementia", "cognitive_disabilities", "developmental_disabilities",
        "person_centered", "complex_illnesses",
    ],
    "domestic": [
        "domestic_tasks", "cooking", "errands", "dressing", "bathing",
        "couple_family", "elders",
    ],
    "medical": [
        "chronic_illness", "assistive_technology", "emergency_preparedness",
        "fragrance_free", "cpr", "emt",
    ],
    "inclusive": [
        "lgbtq", "deaf_community", "limited_english", "visual_impairments",
        "ihss", "anti_bias",
    ],
}
SPECIALTY_THEMES = list(SPECIALTY_CLUSTERS.keys())


def _themed_tag_sample(theme, pool, k_min=3, k_max=5):
    """
    Draw a set of tags mostly from the given theme's cluster (filtered to
    only tags present in `pool`), topping up with random tags from the
    full pool if the cluster is smaller than the chosen sample size.
    """
    k = random.randint(k_min, k_max)
    cluster = [t for t in SPECIALTY_CLUSTERS[theme] if t in pool]
    n_themed = min(k, len(cluster))
    chosen = random.sample(cluster, k=n_themed) if n_themed else []
    remaining = k - len(chosen)
    if remaining > 0:
        others = [t for t in pool if t not in chosen]
        chosen += random.sample(others, k=min(remaining, len(others)))
    return chosen


DAYS_OF_WEEK = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

PERIODS = ["morning", "afternoon", "evening", "overnight"]

# Spread-out real ZIP codes across varying distances from each other so
# location_score_from_distance() lands across all its tiers (10/7/4/2/0 pts)
# instead of clustering at "same ZIP". Mostly Bay Area with a couple of
# far-flung outliers for guaranteed 0-pt / low-score pairs.
ZIP_POOL = [
    "94612",  # Oakland
    "94702",  # Berkeley
    "94103",  # San Francisco
    "94521",  # Concord
    "94010",  # Burlingame
    "95112",  # San Jose
    "94901",  # San Rafael
    "94588",  # Pleasanton
    "95814",  # Sacramento
    "93401",  # San Luis Obispo (far outlier)
    "90001",  # Los Angeles (far outlier)
    "92101",  # San Diego (far outlier)
]


def _generate_availability():
    """Return a {day: [periods]} dict with 2-5 random days."""
    num_days = random.randint(2, 5)
    result = {}
    for day in random.sample(DAYS_OF_WEEK, num_days):
        result[day] = random.sample(PERIODS, k=random.randint(1, 3))
    return result


class Command(BaseCommand):
    help = (
        "Seeds an arbitrary test organization with randomized caregiver/client "
        "members using diverse ZIP codes and the full tag/care-needs pools, "
        "producing a realistic spread of match scores for testing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-name",
            type=str,
            required=True,
            help="Name of the organization to seed (created if it doesn't exist).",
        )
        parser.add_argument(
            "--caregivers",
            type=int,
            default=8,
            help="Number of caregiver profiles to create (default 8).",
        )
        parser.add_argument(
            "--clients",
            type=int,
            default=8,
            help="Number of client profiles to create (default 8).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help=(
                "Remove previously seeded members (caregivers/clients/matches/"
                "schedules) of this org before re-seeding. The org itself and "
                "its admin account are preserved."
            ),
        )

    def handle(self, *args, **options):
        org_name = options["org_name"]
        num_caregivers = options["caregivers"]
        num_clients = options["clients"]
        do_clear = options["clear"]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== seed_random_org : {org_name} ===\n"
        ))

        org, admin_profile = self._get_or_create_org(org_name)

        if do_clear:
            self._clear_seeded_data(org, org_name)

        slug = self._slugify(org_name)

        created_caregivers = []
        for i in range(1, num_caregivers + 1):
            cg = self._create_caregiver(slug, i)
            self._link_caregiver_to_org(cg, org, admin_profile)
            created_caregivers.append(cg)
            self.stdout.write(
                f"  Caregiver {i:>2}: {cg.user_profile.display_name}"
                f"  [ZIP {cg.base_zip_code}, skills: {', '.join(cg.experience_with)}]"
            )

        created_clients = []
        for i in range(1, num_clients + 1):
            cl = self._create_client(slug, i)
            self._link_client_to_org(cl, org, admin_profile)
            created_clients.append(cl)
            self.stdout.write(
                f"  Client    {i:>2}: {cl.user_profile.display_name}"
                f"  [ZIP {cl.base_zip_code}, needs: {', '.join(cl.care_needs)}]"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Done!  Created {len(created_caregivers)} caregivers and "
            f"{len(created_clients)} clients in '{org_name}'."
            f"\n\n  Caregiver logins : {slug}cg1@example.com … {slug}cg{num_caregivers}@example.com / {SEED_PASSWORD}"
            f"\n  Client logins    : {slug}cl1@example.com … {slug}cl{num_clients}@example.com / {SEED_PASSWORD}"
            f"\n\n  ZIPs and tags were drawn randomly from a diverse pool, so "
            f"match scores across this org should now vary widely instead of "
            f"clustering high."
        ))
        self.stdout.write("")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _slugify(self, name):
        """Make a short lowercase, alnum-only prefix for generated emails."""
        slug = "".join(ch for ch in name.lower() if ch.isalnum())
        return slug[:12] or "org"

    def _get_or_create_org(self, org_name):
        from accounts.models import UserProfile, StaffProfile
        from organizations.models import Organization, OrganizationStaff

        try:
            org = Organization.objects.get(name=org_name)
            self.stdout.write(f"Found existing organisation: {org_name}")
            admin_profile = None
            if org.primary_admin_id:
                admin_profile = org.primary_admin.user_profile
            if admin_profile is None:
                # Fall back to any active staff member on this org
                staff_rel = OrganizationStaff.objects.filter(
                    organization=org, status="active"
                ).select_related("staff_profile__user_profile").first()
                if staff_rel:
                    admin_profile = staff_rel.staff_profile.user_profile
            if admin_profile is None:
                raise CommandError(
                    f"Organization '{org_name}' exists but has no admin/staff "
                    "account to attribute approvals to. Please add a staff "
                    "member first."
                )
            return org, admin_profile
        except Organization.DoesNotExist:
            pass

        # Create a fresh org + admin account
        slug = self._slugify(org_name)
        admin_email = f"{slug}-admin@example.com"
        admin_user, created = User.objects.get_or_create(
            email=admin_email,
            defaults={
                "username": admin_email,
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

        org_zip = random.choice(ZIP_POOL)
        org = Organization.objects.create(
            name=org_name,
            city="",
            zip_code=org_zip,
            contact_email=admin_email,
            primary_admin=staff_profile,
        )

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

        self.stdout.write(
            f"Created organisation: {org_name}  (admin: {admin_email} / {SEED_PASSWORD})"
        )
        return org, admin_profile

    def _clear_seeded_data(self, org, org_name):
        """Remove previously seeded members of this org (keeps org + admin)."""
        from registry.models import (
            OrganizationCaregiver, OrganizationClient,
            Schedule, ScheduleEntryRating, CaregiverProfile, ClientProfile,
        )
        from matching.models import Match

        slug = self._slugify(org_name)

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

        removed_cg = 0
        for cg in CaregiverProfile.objects.filter(pk__in=cg_profiles):
            user = cg.user_profile.user
            if f"{slug}cg" in user.email:
                user.delete()
                removed_cg += 1

        removed_cl = 0
        for cl in ClientProfile.objects.filter(pk__in=cl_profiles):
            user = cl.user_profile.user
            if f"{slug}cl" in user.email:
                user.delete()
                removed_cl += 1

        self.stdout.write(self.style.WARNING(
            f"  Cleared: {match_count} matches, {sched_count} schedules, "
            f"{rating_count} ratings, {removed_cg} caregivers, "
            f"{removed_cl} clients."
        ))

    def _create_caregiver(self, slug, index):
        from accounts.models import UserProfile
        from registry.models import CaregiverProfile

        email = f"{slug}cg{index}@example.com"
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        zip_code = random.choice(ZIP_POOL)

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

        theme = random.choice(SPECIALTY_THEMES)
        experience = _themed_tag_sample(theme, EXPERIENCE_OPTIONS)

        profile, _ = CaregiverProfile.objects.get_or_create(

            user_profile=user_profile,
            defaults={
                "base_zip_code": zip_code,
                "willing_to_work_cities": [],
                "transportation": random.sample(
                    ["licensed_driver", "vehicle_access", "insured"],
                    k=random.randint(0, 3),
                ),
                "availability": _generate_availability(),
                "hours_looking_for": random.choice(
                    ["few_hours", "part_time", "full_time", "flexible"]
                ),
                "desired_hours_per_week": random.choice([10, 15, 20, 25, 30, 40]),
                "certified_ihss_worker": random.choice([True, False]),
                "additional_certifications": random.choice(
                    ["", "CPR Certified", "First Aid", "CNA License"]
                ),
                "experience_with": experience,
                "languages_spoken": random.sample(
                    ["english", "spanish", "cantonese", "mandarin"],
                    k=random.randint(1, 2),
                ),
                "pathogen_protocols": random.sample(
                    ["n95_at_work", "masking_indoors"], k=random.randint(0, 2)
                ),
                "rate": random.choice(["17_20", "20_25", "25_30", "30_50"]),
                "bio": (
                    f"Careworker with {random.randint(1, 12)} years of experience."
                ),
                "wants_training_updates": random.choice([True, False]),
            },
        )
        return profile

    def _create_client(self, slug, index):
        from accounts.models import UserProfile
        from registry.models import ClientProfile

        email = f"{slug}cl{index}@example.com"
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        zip_code = random.choice(ZIP_POOL)

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
                "address": f"{random.randint(100, 9999)} Main St, CA {zip_code}",
            },
        )

        theme = random.choice(SPECIALTY_THEMES)
        care_needs = _themed_tag_sample(theme, CARE_NEEDS_OPTIONS)

        profile, _ = ClientProfile.objects.get_or_create(

            user_profile=user_profile,
            defaults={
                "base_zip_code": zip_code,
                "attendant_care_programs": random.sample(
                    ["ihss", "wpcs", "out_of_pocket"], k=random.randint(1, 2)
                ),
                "languages_preferred": random.sample(
                    ["english", "spanish", "cantonese", "mandarin"],
                    k=random.randint(1, 2),
                ),
                "availability": _generate_availability(),
                "schedule_flexibility": random.choice([True, False]),
                "hours_per_week": random.choice([10, 20, 30, 40]),
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
