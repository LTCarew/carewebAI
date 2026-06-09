"""
Django management command to seed caregiver and client profiles for testing.

Usage:
    python manage.py seed_profiles
    python manage.py seed_profiles --caregivers 50 --clients 30
    python manage.py seed_profiles --clear
"""
import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import UserProfile
from registry.models import CaregiverProfile, ClientProfile

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds the database with fake caregiver and client profiles for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--caregivers',
            type=int,
            default=10,
            help='Number of caregiver profiles to create'
        )
        parser.add_argument(
            '--clients',
            type=int,
            default=10,
            help='Number of client profiles to create'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing profiles before seeding'
        )

    def handle(self, *args, **options):
        num_caregivers = options['caregivers']
        num_clients = options['clients']
        clear = options['clear']

        if clear:
            self.stdout.write('Clearing existing profiles...')
            CaregiverProfile.objects.all().delete()
            ClientProfile.objects.all().delete()
            # Also clean up orphaned users/profiles
            self.stdout.write(self.style.SUCCESS('✓ Cleared existing profiles'))

        self.stdout.write(f'\nCreating {num_caregivers} caregivers...')
        for i in range(num_caregivers):
            self._create_caregiver(i + 1)
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {num_caregivers} caregivers'))

        self.stdout.write(f'\nCreating {num_clients} clients...')
        for i in range(num_clients):
            self._create_client(i + 1)
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {num_clients} clients'))
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ Done! Created {num_caregivers} caregivers and {num_clients} clients'))

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
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={'username': email}
        )
        user.set_unusable_password()
        user.save()
        
        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'name': name,
                'phone': phone,
                'email': email,
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
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={'username': email}
        )
        user.set_unusable_password()
        user.save()
        
        user_profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'name': name,
                'phone': phone,
                'email': email,
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
        """Generate random availability schedule."""
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        times = ['08:00', '09:00', '10:00', '12:00', '14:00', '16:00', '18:00']
        
        availability = {}
        num_days = random.randint(2, 5)
        
        for day in random.sample(days, num_days):
            start = random.choice(times[:4])
            end = random.choice(times[4:])
            availability[day] = {'start': start, 'end': end}
        
        return availability
