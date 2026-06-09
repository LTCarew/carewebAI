from django import forms
from django.db import transaction
from organizations.models import Organization
from accounts.models import UserProfile
from .models import (
    CaregiverProfile,
    ClientProfile,
    OrganizationCaregiver,
    OrganizationClient,
    CONTACT_PREFERENCES,
    TRANSPORTATION_CHOICES,
    EXPERIENCE_CHOICES,
    LANGUAGE_CHOICES,
    PATHOGEN_PROTOCOL_CHOICES,
    ATTENDANT_PROGRAM_CHOICES,
    CARE_NEEDS_CHOICES,
    HOURS_LOOKING_FOR_CHOICES,
    RATE_CHOICES,
    PRONOUN_CHOICES,
)
from .services import get_or_create_user_from_email


TIME_CHOICES = [
    ("", "Select time"),
    ("06:00", "6:00 AM"),
    ("07:00", "7:00 AM"),
    ("08:00", "8:00 AM"),
    ("09:00", "9:00 AM"),
    ("10:00", "10:00 AM"),
    ("11:00", "11:00 AM"),
    ("12:00", "12:00 PM"),
    ("13:00", "1:00 PM"),
    ("14:00", "2:00 PM"),
    ("15:00", "3:00 PM"),
    ("16:00", "4:00 PM"),
    ("17:00", "5:00 PM"),
    ("18:00", "6:00 PM"),
    ("19:00", "7:00 PM"),
    ("20:00", "8:00 PM"),
    ("21:00", "9:00 PM"),
    ("22:00", "10:00 PM"),
]


DAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def apply_bulma_classes(form):
    """Apply Bulma CSS classes to standard Django form widgets."""
    for field_name, field in form.fields.items():
        if isinstance(field.widget, forms.CheckboxSelectMultiple):
            continue

        if isinstance(field.widget, forms.CheckboxInput):
            continue

        if isinstance(field.widget, forms.Textarea):
            field.widget.attrs["class"] = "textarea"

        elif isinstance(field.widget, forms.Select):
            field.widget.attrs["class"] = "select"

        else:
            field.widget.attrs["class"] = "input"


class AvailabilityMixin:
    def add_availability_fields(self):
        for day in DAYS:
            self.fields[f"{day}_available"] = forms.BooleanField(
                required=False,
                label=day.title()
            )
            self.fields[f"{day}_start"] = forms.ChoiceField(
                choices=TIME_CHOICES,
                required=False,
                label=f"{day.title()} Start"
            )
            self.fields[f"{day}_end"] = forms.ChoiceField(
                choices=TIME_CHOICES,
                required=False,
                label=f"{day.title()} End"
            )

    def build_availability_json(self):
        availability = {}

        for day in DAYS:
            is_available = self.cleaned_data.get(f"{day}_available")
            start = self.cleaned_data.get(f"{day}_start")
            end = self.cleaned_data.get(f"{day}_end")

            if is_available and start and end:
                availability[day] = {
                    "start": start,
                    "end": end
                }

        return availability


class CaregiverApplicationForm(AvailabilityMixin, forms.Form):
    """
    Form for caregiver applications.
    Creates User, UserProfile, and CaregiverProfile.
    Applicants go into a general pool - organizations add them later.
    """
    name = forms.CharField(max_length=255)
    phone = forms.CharField(max_length=25)
    email = forms.EmailField()
    contact_preferences = forms.MultipleChoiceField(
        choices=CONTACT_PREFERENCES,
        widget=forms.CheckboxSelectMultiple
    )
    pronouns = forms.ChoiceField(choices=PRONOUN_CHOICES, required=False)
    
    base_zip_code = forms.CharField(max_length=10)
    willing_to_work_cities = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    transportation = forms.MultipleChoiceField(
        choices=TRANSPORTATION_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    hours_looking_for = forms.ChoiceField(choices=HOURS_LOOKING_FOR_CHOICES)
    
    certified_ihss_worker = forms.BooleanField(required=False)
    additional_certifications = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False
    )
    
    experience_with = forms.MultipleChoiceField(
        choices=EXPERIENCE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    languages_spoken = forms.MultipleChoiceField(
        choices=LANGUAGE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    pathogen_protocols = forms.MultipleChoiceField(
        choices=PATHOGEN_PROTOCOL_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    rate = forms.ChoiceField(choices=RATE_CHOICES)
    bio = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), required=False)
    wants_training_updates = forms.BooleanField(required=False)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        cities = (
            Organization.objects
            .exclude(city="")
            .values_list("city", "city")
            .distinct()
            .order_by("city")
        )
        self.fields["willing_to_work_cities"].choices = list(cities)
        
        self.add_availability_fields()
        apply_bulma_classes(self)
    
    @transaction.atomic
    def save(self):
        """
        Create User, UserProfile, and CaregiverProfile.
        Caregiver goes into general pool - organizations can add them later.
        """
        # 1. Get or create User
        user = get_or_create_user_from_email(
            email=self.cleaned_data['email'],
            name=self.cleaned_data['name']
        )
        
        # 2. Create or update UserProfile
        user_profile, _ = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                'name': self.cleaned_data['name'],
                'phone': self.cleaned_data['phone'],
                'email': self.cleaned_data['email'],
                'pronouns': self.cleaned_data.get('pronouns', ''),
                'contact_preferences': self.cleaned_data['contact_preferences'],
            }
        )
        
        # 3. Create or update CaregiverProfile
        caregiver_profile, _ = CaregiverProfile.objects.update_or_create(
            user_profile=user_profile,
            defaults={
                'base_zip_code': self.cleaned_data['base_zip_code'],
                'willing_to_work_cities': self.cleaned_data['willing_to_work_cities'],
                'transportation': self.cleaned_data['transportation'],
                'availability': self.build_availability_json(),
                'hours_looking_for': self.cleaned_data['hours_looking_for'],
                'certified_ihss_worker': self.cleaned_data['certified_ihss_worker'],
                'additional_certifications': self.cleaned_data.get('additional_certifications', ''),
                'experience_with': self.cleaned_data['experience_with'],
                'languages_spoken': self.cleaned_data['languages_spoken'],
                'pathogen_protocols': self.cleaned_data['pathogen_protocols'],
                'rate': self.cleaned_data['rate'],
                'bio': self.cleaned_data.get('bio', ''),
                'wants_training_updates': self.cleaned_data.get('wants_training_updates', False),
            }
        )
        
        return caregiver_profile


class ClientApplicationForm(AvailabilityMixin, forms.Form):
    """
    Form for client applications.
    Creates User, UserProfile, and ClientProfile.
    Applicants go into a general pool - organizations add them later.
    """
    name = forms.CharField(max_length=255)
    phone = forms.CharField(max_length=25)
    email = forms.EmailField()
    contact_preferences = forms.MultipleChoiceField(
        choices=CONTACT_PREFERENCES,
        widget=forms.CheckboxSelectMultiple
    )
    pronouns = forms.ChoiceField(choices=PRONOUN_CHOICES, required=False)
    
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    base_zip_code = forms.CharField(max_length=10)
    
    attendant_care_programs = forms.MultipleChoiceField(
        choices=ATTENDANT_PROGRAM_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    languages_preferred = forms.MultipleChoiceField(
        choices=LANGUAGE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    schedule_flexibility = forms.BooleanField(required=False)
    hours_per_week = forms.IntegerField(required=False, min_value=0)
    
    care_needs = forms.MultipleChoiceField(
        choices=CARE_NEEDS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    additional_care_needs = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False
    )
    
    pathogen_protocol_preferences = forms.MultipleChoiceField(
        choices=PATHOGEN_PROTOCOL_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_availability_fields()
        apply_bulma_classes(self)
    
    @transaction.atomic
    def save(self):
        """
        Create User, UserProfile, and ClientProfile.
        Client goes into general pool - organizations can add them later.
        """
        # 1. Get or create User
        user = get_or_create_user_from_email(
            email=self.cleaned_data['email'],
            name=self.cleaned_data['name']
        )
        
        # 2. Create or update UserProfile
        user_profile, _ = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                'name': self.cleaned_data['name'],
                'phone': self.cleaned_data['phone'],
                'email': self.cleaned_data['email'],
                'pronouns': self.cleaned_data.get('pronouns', ''),
                'contact_preferences': self.cleaned_data['contact_preferences'],
                'address': self.cleaned_data['address'],
            }
        )
        
        # 3. Create or update ClientProfile
        client_profile, _ = ClientProfile.objects.update_or_create(
            user_profile=user_profile,
            defaults={
                'base_zip_code': self.cleaned_data['base_zip_code'],
                'attendant_care_programs': self.cleaned_data['attendant_care_programs'],
                'languages_preferred': self.cleaned_data['languages_preferred'],
                'availability': self.build_availability_json(),
                'schedule_flexibility': self.cleaned_data.get('schedule_flexibility', False),
                'hours_per_week': self.cleaned_data.get('hours_per_week'),
                'care_needs': self.cleaned_data['care_needs'],
                'additional_care_needs': self.cleaned_data.get('additional_care_needs', ''),
                'pathogen_protocol_preferences': self.cleaned_data['pathogen_protocol_preferences'],
            }
        )
        
        return client_profile


# ==============================================
# Support Coordinator Forms
# ==============================================

class CoordinatorInviteForm(forms.Form):
    """
    Form for clients to invite support coordinators.
    Sends an email invitation with a unique signup link.
    """
    email = forms.EmailField(
        label="Coordinator Email",
        help_text="Email address of the person you want to invite as your support coordinator"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bulma_classes(self)


class CoordinatorSignupForm(forms.Form):
    """
    Form for invited coordinators to sign up and accept the invitation.
    Creates User, UserProfile, SupportCoordinatorProfile, and ClientCoordinator records.
    """
    # Pre-filled from invite (read-only)
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'readonly': 'readonly'})
    )
    
    # Coordinator information
    name = forms.CharField(max_length=255, label="Full Name")
    phone = forms.CharField(max_length=25, label="Phone Number")
    
    contact_preferences = forms.MultipleChoiceField(
        choices=CONTACT_PREFERENCES,
        widget=forms.CheckboxSelectMultiple,
        label="Preferred Contact Methods"
    )
    
    pronouns = forms.ChoiceField(
        choices=PRONOUN_CHOICES,
        required=False,
        label="Pronouns"
    )
    
    # Coordinator-specific fields
    relationship_to_clients = forms.CharField(
        max_length=100,
        label="Relationship to Client",
        help_text="E.g., Family member, Friend, Agency representative, etc."
    )
    
    credentials = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Professional Credentials",
        help_text="List any relevant professional credentials or qualifications"
    )
    
    certifications = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Certifications",
        help_text="List any relevant certifications"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bulma_classes(self)
    
    @transaction.atomic
    def save(self, invite):
        """
        Create User, UserProfile, SupportCoordinatorProfile, and ClientCoordinator.
        Mark the invitation as used.
        
        Args:
            invite: CoordinatorInvite instance
        
        Returns:
            ClientCoordinator instance
        """
        from .models import SupportCoordinatorProfile, ClientCoordinator
        from django.utils import timezone
        
        # 1. Get or create User
        user = get_or_create_user_from_email(
            email=self.cleaned_data['email'],
            name=self.cleaned_data['name']
        )
        
        # 2. Create or update UserProfile
        user_profile, _ = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                'name': self.cleaned_data['name'],
                'phone': self.cleaned_data['phone'],
                'email': self.cleaned_data['email'],
                'pronouns': self.cleaned_data.get('pronouns', ''),
                'contact_preferences': self.cleaned_data['contact_preferences'],
            }
        )
        
        # 3. Create or update SupportCoordinatorProfile
        coordinator_profile, _ = SupportCoordinatorProfile.objects.update_or_create(
            user_profile=user_profile,
            defaults={
                'relationship_to_clients': self.cleaned_data['relationship_to_clients'],
                'credentials': self.cleaned_data.get('credentials', ''),
                'certifications': self.cleaned_data.get('certifications', ''),
            }
        )
        
        # 4. Create ClientCoordinator relationship
        client_coordinator, _ = ClientCoordinator.objects.update_or_create(
            client_profile=invite.client_profile,
            coordinator_profile=coordinator_profile,
            defaults={
                'status': 'active',  # Auto-active since they accepted invite
                'invited_by': invite.invited_by,
                'accepted_at': timezone.now(),
            }
        )
        
        # 5. Mark invitation as used
        invite.used_at = timezone.now()
        invite.save()
        
        return client_coordinator
