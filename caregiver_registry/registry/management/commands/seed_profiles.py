"""
Django management command to seed caregiver and client profiles for testing.

Usage:
    # Bulk seeding (random fake data, no real password)
    python manage.py seed_profiles
    python manage.py seed_profiles --caregivers 50 --clients 30
    python manage.py seed_profiles --clear

    # Single profile with custom credentials (no org assignment, usable password)
    python manage.py seed_profiles --single --role caregiver --username testcg --password TestPass123
    python manage.py seed_profiles --single --role client   --username testcl --password TestPass123
    python manage.py seed_profiles --single --role caregiver --username testcg --password TestPass123 --email me@example.com --name "Alex Smith"

Notes:
    --single profiles are NOT assigned to any organization.
    The admin/staff must add and approve them through the normal dashboard workflow.
"""
import random
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from accounts.models import UserProfile
from registry.models import CaregiverProfile, ClientProfile

User = get_user_model()

# Shared password for all bulk-seeded users (caregivers and clients).
# Do NOT use in production.
SEEDED_USER_PASSWORD = "carewebai2026"


class Command(BaseCommand):
    help = 'Seeds the database with fake caregiver and client profiles for testing'

    def add_arguments(self, parser):
        # ── Bulk mode flags ────────────────────────────────────────────────────
        parser.add_argument(
            '--caregivers',
            type=int,
            default=10,
            help='Number of caregiver profiles to create (bulk mode, default 10)'
        )
        parser.add_argument(
            '--clients',
            type=int,
            default=10,
            help='Number of client profiles to create (bulk mode, default 10)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing CaregiverProfile and ClientProfile rows before seeding'
        )

        # ── Single-profile mode flags ──────────────────────────────────────────
        parser.add_argument(
            '--single',
            action='store_true',
            help='Create exactly one profile with custom credentials instead of bulk fake data'
        )
        parser.add_argument(
            '--role',
            type=str,
            choices=['caregiver', 'client'],
            help='Role for single-profile mode: caregiver or client'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Username (login) for the new user (single mode)'
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Password for the new user (single mode)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default=None,
            help='Email address (single mode, optional — defaults to username@example.com)'
        )
        parser.add_argument(
            '--name',
            type=str,
            default=None,
            help='Display name (single mode, optional — defaults to capitalized username)'
        )

    def handle(self, *args, **options):
        # ── Single-profile mode ────────────────────────────────────────────────
        if options['single']:
            role = options.get('role')
            username = options.get('username')
            password = options.get('password')

            if not role:
                raise CommandError("--role is required when using --single. Use: --role caregiver  OR  --role client")
            if not username:
                raise CommandError("--username is required when using --single.")
            if not password:
                raise CommandError("--password is required when using --single.")

            email = options['email'] or f"{username}@example.com"
            name = options['name'] or username.replace('_', ' ').replace('-', ' ').title()

            if role == 'caregiver':
                profile = self._create_single_caregiver(username, password, email, name)
                self.stdout.write(self.style.SUCCESS(
                    f'\n✓ Created caregiver profile: {name}'
                    f'\n  username : {username}'
                    f'\n  email    : {email}'
                    f'\n  password : {password}'
                    f'\n  profile  : CaregiverProfile #{profile.pk}'
                    f'\n\n  → Log in as this user, then have staff add/approve them from the org dashboard.'
                ))
            else:
                profile = self._create_single_client(username, password, email, name)
                self.stdout.write(self.style.SUCCESS(
                    f'\n✓ Created client profile: {name}'
                    f'\n  username : {username}'
                    f'\n  email    : {email}'
                    f'\n  password : {password}'
                    f'\n  profile  : ClientProfile #{profile.pk}'
                    f'\n\n  → Log in as this user, then have staff add/approve them from the org dashboard.'
                ))
            return

        # ── Bulk mode ──────────────────────────────────────────────────────────
        num_caregivers = options['caregivers']
        num_clients = options['clients']
        clear = options['clear']

        if clear:
            self.stdout.write('Clearing existing profiles...')
            CaregiverProfile.objects.all().delete()
            ClientProfile.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('✓ Cleared existing profiles'))

        self.stdout.write(f'\nCreating {num_caregivers} caregivers...')
        for i in range(num_caregivers):
            self._create_caregiver(i + 1)

        self.stdout.write(self.style.SUCCESS(f'✓ Created {num_caregivers} caregivers'))

        self.stdout.write(f'\nCreating {num_clients} clients...')
        for i in range(num_clients):
            self._create_client(i + 1)

        self.stdout.write(self.style.SUCCESS(f'✓ Created {num_clients} clients'))

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Done! Created {num_caregivers} caregivers and {num_clients} clients'
            f'\n  Shared login password : {SEEDED_USER_PASSWORD}'
            f'\n  Caregiver logins      : caregiver1@example.com … caregiver{num_caregivers}@example.com'
            f'\n  Client logins         : client1@example.com … client{num_clients}@example.com'
        ))

    # ── Single-profile helpers ─────────────────────────────────────────────────

    def _create_single_caregiver(self, username, password, email, name):
        """Create one caregiver with a real usable password, no org assignment."""
        if User.objects.filter(username=username).exists():
            raise CommandError(f"A user with username '{username}' already exists.")
        if User.objects.filter(email=email).exists():
            raise CommandError(f"A user with email '{email}' already exists.")

        parts = name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'phone': '',
            }
        )

        profile, created = CaregiverProfile.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                'base_zip_code': '',
                'willing_to_work_cities': [],
                'transportation': [],
                'availability': {},
                'hours_looking_for': 'flexible',
                'certified_ihss_worker': False,
                'additional_certifications': '',
                'experience_with': [],
                'languages_spoken': ['english'],
                'pathogen_protocols': [],
                'rate': '',
                'bio': '',
                'wants_training_updates': False,
            }
        )

        if not created:
            raise CommandError(f"A CaregiverProfile already exists for user '{username}'.")

        return profile

    def _create_single_client(self, username, password, email, name):
        """Create one client with a real usable password, no org assignment."""
        if User.objects.filter(username=username).exists():
            raise CommandError(f"A user with username '{username}' already exists.")
        if User.objects.filter(email=email).exists():
            raise CommandError(f"A user with email '{email}' already exists.")

        parts = name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'phone': '',
            }
        )

        profile, created = ClientProfile.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                'base_zip_code': '',
                'attendant_care_programs': [],
                'languages_preferred': ['english'],
                'availability': {},
                'schedule_flexibility': True,
                'hours_per_week': None,
                'care_needs': [],
                'additional_care_needs': '',
                'pathogen_protocol_preferences': [],
            }
        )

        if not created:
            raise CommandError(f"A ClientProfile already exists for user '{username}'.")

        return profile

    def _create_caregiver(self, index):
        """Create a fake caregiver profile."""
        # Generate fake data
        first_names = ['Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley', 'Avery', 'Quinn', 'Sage', 'Drew']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
        
        first = random.choice(first_names)
        last = random.choice(last_names)
        name = f"{first} {last}"
        email = f"caregiver{index}@example.com"
        phone = f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
        
        # Create user and profile
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': first,
                'last_name': last,
            }
        )
        user.set_password(SEEDED_USER_PASSWORD)
        user.is_active = True
        if not created:
            user.first_name = first
            user.last_name = last
        user.save()

        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'phone': phone,
                'pronouns': random.choice(['she_her', 'he_him', 'they_them', '']),
                'contact_preferences': random.sample(['phone', 'email', 'text'], k=random.randint(1, 2)),
            }
        )

        # Create caregiver profile with realistic data
        CaregiverProfile.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                'base_zip_code': f"{random.randint(90000, 96000)}",
                'willing_to_work_cities': random.sample(
                    ['Oakland', 'Berkeley', 'San Francisco', 'Alameda', 'Richmond'],
                    k=random.randint(1, 3)
                ),
                'transportation': random.sample(
                    ['licensed_driver', 'vehicle_access', 'insured'],
                    k=random.randint(0, 3)
                ),
                'availability': self._generate_availability(),
                'hours_looking_for': random.choice([
                    'few_hours', 'part_time', 'full_time', 'flexible'
                ]),
                'desired_hours_per_week': random.choice([10, 15, 20, 25, 30, 40, None]),
                'certified_ihss_worker': random.choice([True, False]),
                'additional_certifications': random.choice([
                    '', 'CPR Certified', 'First Aid', 'CNA License'
                ]),
                'experience_with': random.sample(
                    ['domestic_tasks', 'cooking', 'bathing', 'dressing', 'elders', 'cognitive_disabilities'],
                    k=random.randint(2, 5)
                ),
                'languages_spoken': random.sample(
                    ['english', 'spanish', 'cantonese'],
                    k=random.randint(1, 2)
                ),
                'pathogen_protocols': random.sample(
                    ['n95_at_work', 'masking_indoors'],
                    k=random.randint(0, 2)
                ),
                'rate': random.choice(['17_20', '20_25', '25_30', '30_50']),
                'bio': f"Experienced caregiver with a passion for helping others. {random.randint(2, 10)} years of experience.",
                'wants_training_updates': random.choice([True, False]),
            }
        )

    def _create_client(self, index):
        """Create a fake client profile."""
        # Generate fake data
        first_names = ['Maria', 'James', 'Patricia', 'Robert', 'Linda', 'Michael', 'Barbara', 'William', 'Elizabeth', 'David']
        last_names = ['Anderson', 'Thomas', 'Jackson', 'White', 'Harris', 'Martin', 'Thompson', 'Garcia', 'Martinez', 'Robinson']
        
        first = random.choice(first_names)
        last = random.choice(last_names)
        name = f"{first} {last}"
        email = f"client{index}@example.com"
        phone = f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
        
        # Create user and profile
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': first,
                'last_name': last,
            }
        )
        user.set_password(SEEDED_USER_PASSWORD)
        user.is_active = True
        if not created:
            user.first_name = first
            user.last_name = last
        user.save()

        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'phone': phone,
                'pronouns': random.choice(['she_her', 'he_him', 'they_them', '']),
                'contact_preferences': random.sample(['phone', 'email', 'text'], k=random.randint(1, 2)),
                'address': f"{random.randint(100, 9999)} Main St, Oakland, CA",
            }
        )
        
        # Create client profile with realistic data
        ClientProfile.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                'base_zip_code': f"{random.randint(90000, 96000)}",
                'attendant_care_programs': random.sample(
                    ['ihss', 'wpcs', 'out_of_pocket'],
                    k=random.randint(1, 2)
                ),
                'languages_preferred': random.sample(
                    ['english', 'spanish'],
                    k=random.randint(1, 2)
                ),
                'availability': self._generate_availability(),
                'schedule_flexibility': random.choice([True, False]),
                'hours_per_week': random.choice([10, 20, 30, 40, None]),
                'care_needs': random.sample(
                    ['domestic_tasks', 'cooking', 'bathing', 'dressing', 'errands', 'lifting_transfers'],
                    k=random.randint(2, 5)
                ),
                'additional_care_needs': random.choice([
                    '', 'Assistance with medications', 'Transportation to appointments'
                ]),
                'pathogen_protocol_preferences': random.sample(
                    ['n95_at_work', 'masking_indoors'],
                    k=random.randint(0, 2)
                ),
            }
        )

    def _generate_availability(self):
        """Generate random availability using day -> list-of-periods format.

        Periods: morning (6 AM-12 PM), afternoon (12-5 PM),
                 evening (5-10 PM), overnight (10 PM-6 AM)
        """
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        periods = ['morning', 'afternoon', 'evening', 'overnight']

        availability = {}
        num_days = random.randint(2, 5)

        for day in random.sample(days, num_days):
            selected = random.sample(periods, k=random.randint(1, 3))
            availability[day] = selected

        return availability
