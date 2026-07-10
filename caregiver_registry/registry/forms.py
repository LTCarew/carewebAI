from django import forms
from django.db import transaction
from django.contrib.auth import get_user_model
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

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Availability constants
# ─────────────────────────────────────────────────────────────────────────────

DAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

TIME_PERIOD_CHOICES = [
    ("morning",   "Morning       6:00 AM – 12:00 PM"),
    ("afternoon", "Afternoon   12:00 PM – 5:00 PM"),
    ("evening",   "Evening       5:00 PM – 10:00 PM"),
    ("overnight", "Overnight   10:00 PM – 6:00 AM"),
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
    """
    Adds per-day multiple-choice time-period checkboxes to a form.

    For each day (Monday–Sunday) this adds a `{day}_periods` field with
    choices: Morning, Afternoon, Evening, Overnight.

    JSON format stored on the profile:
        {
          "monday": ["morning", "afternoon"],
          "tuesday": ["overnight"]
        }
    Only days with at least one period selected are stored.
    """

    def add_availability_fields(self):
        for day in DAYS:
            self.fields[f"{day}_periods"] = forms.MultipleChoiceField(
                choices=TIME_PERIOD_CHOICES,
                widget=forms.CheckboxSelectMultiple,
                required=False,
                label=day.title(),
            )

    def build_availability_json(self):
        availability = {}
        for day in DAYS:
            periods = self.cleaned_data.get(f"{day}_periods") or []
            if periods:
                availability[day] = list(periods)
        return availability


# ─────────────────────────────────────────────────────────────────────────────
# Caregiver Application Form
# ─────────────────────────────────────────────────────────────────────────────

class CaregiverApplicationForm(AvailabilityMixin, forms.Form):
    """
    Form for caregiver applications.
    Creates User, UserProfile, and CaregiverProfile.
    Applicants go into a general pool — organizations add them later.
    """
    # Account credentials — identity lives on auth User
    first_name = forms.CharField(max_length=150, label="First Name")
    last_name = forms.CharField(max_length=150, label="Last Name")
    username = forms.CharField(
        max_length=150,
        help_text="Choose a username for your account"
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        help_text="Choose a secure password"
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
        help_text="Enter the same password again"
    )

    # Personal information
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

    desired_hours_per_week = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=168,
        label="Desired work hours per week",
        help_text="How many hours per week are you looking to work?"
    )

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

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken. Please choose another.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The two password fields must match.")

        return cleaned_data

    @transaction.atomic
    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            is_active=False,
        )

        user_profile = UserProfile.objects.create(
            user=user,
            phone=self.cleaned_data['phone'],
            pronouns=self.cleaned_data.get('pronouns', ''),
            contact_preferences=self.cleaned_data['contact_preferences'],
        )

        caregiver_profile = CaregiverProfile.objects.create(
            user_profile=user_profile,
            base_zip_code=self.cleaned_data['base_zip_code'],
            willing_to_work_cities=self.cleaned_data['willing_to_work_cities'],
            transportation=self.cleaned_data['transportation'],
            availability=self.build_availability_json(),
            hours_looking_for=self.cleaned_data['hours_looking_for'],
            desired_hours_per_week=self.cleaned_data.get('desired_hours_per_week'),
            certified_ihss_worker=self.cleaned_data['certified_ihss_worker'],
            additional_certifications=self.cleaned_data.get('additional_certifications', ''),
            experience_with=self.cleaned_data['experience_with'],
            languages_spoken=self.cleaned_data['languages_spoken'],
            pathogen_protocols=self.cleaned_data['pathogen_protocols'],
            rate=self.cleaned_data['rate'],
            bio=self.cleaned_data.get('bio', ''),
            wants_training_updates=self.cleaned_data.get('wants_training_updates', False),
        )

        return caregiver_profile


# ─────────────────────────────────────────────────────────────────────────────
# Client Application Form
# ─────────────────────────────────────────────────────────────────────────────

class ClientApplicationForm(AvailabilityMixin, forms.Form):
    """
    Form for client applications.
    Creates User, UserProfile, and ClientProfile.
    Applicants go into a general pool — organizations add them later.
    """
    # Account credentials — identity lives on auth User
    first_name = forms.CharField(max_length=150, label="First Name")
    last_name = forms.CharField(max_length=150, label="Last Name")
    username = forms.CharField(
        max_length=150,
        help_text="Choose a username for your account"
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        help_text="Choose a secure password"
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
        help_text="Enter the same password again"
    )

    # Personal information
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
    hours_per_week = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=168,
        label="Desired care hours per week",
        help_text="How many hours per week do you need care services?"
    )

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

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken. Please choose another.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The two password fields must match.")

        return cleaned_data

    @transaction.atomic
    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            is_active=False,
        )

        user_profile = UserProfile.objects.create(
            user=user,
            phone=self.cleaned_data['phone'],
            pronouns=self.cleaned_data.get('pronouns', ''),
            contact_preferences=self.cleaned_data['contact_preferences'],
            address=self.cleaned_data['address'],
        )

        client_profile = ClientProfile.objects.create(
            user_profile=user_profile,
            base_zip_code=self.cleaned_data['base_zip_code'],
            attendant_care_programs=self.cleaned_data['attendant_care_programs'],
            languages_preferred=self.cleaned_data['languages_preferred'],
            availability=self.build_availability_json(),
            schedule_flexibility=self.cleaned_data.get('schedule_flexibility', False),
            hours_per_week=self.cleaned_data.get('hours_per_week'),
            care_needs=self.cleaned_data['care_needs'],
            additional_care_needs=self.cleaned_data.get('additional_care_needs', ''),
            pathogen_protocol_preferences=self.cleaned_data['pathogen_protocol_preferences'],
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
    Identity (name, email) is saved on the auth User.

    Password fields allow the coordinator to set credentials they can use to
    log back in after the initial invite session ends.
    """
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'readonly': 'readonly'})
    )

    first_name = forms.CharField(max_length=150, label="First Name")
    last_name = forms.CharField(max_length=150, label="Last Name")

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        help_text="Choose a secure password you'll use to log in later."
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
        help_text="Enter the same password again to confirm."
    )

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

    def clean(self):
        cleaned_data = super().clean()
        pw1 = cleaned_data.get("password1")
        pw2 = cleaned_data.get("password2")
        if pw1 and pw2 and pw1 != pw2:
            raise forms.ValidationError("The two password fields must match.")
        return cleaned_data

    @transaction.atomic
    def save(self, invite):
        from .models import SupportCoordinatorProfile, ClientCoordinator
        from django.utils import timezone

        user = get_or_create_user_from_email(
            email=self.cleaned_data['email'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
        )

        # Set a real, usable password so the coordinator can log in later.
        user.set_password(self.cleaned_data['password1'])
        user.is_active = True
        user.save()

        user_profile, _ = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                'phone': self.cleaned_data['phone'],
                'pronouns': self.cleaned_data.get('pronouns', ''),
                'contact_preferences': self.cleaned_data['contact_preferences'],
            }
        )

        coordinator_profile, _ = SupportCoordinatorProfile.objects.update_or_create(
            user_profile=user_profile,
            defaults={
                'relationship_to_clients': self.cleaned_data['relationship_to_clients'],
                'credentials': self.cleaned_data.get('credentials', ''),
                'certifications': self.cleaned_data.get('certifications', ''),
            }
        )

        client_coordinator, _ = ClientCoordinator.objects.update_or_create(
            client_profile=invite.client_profile,
            coordinator_profile=coordinator_profile,
            defaults={
                'status': 'active',
                'invited_by': invite.invited_by,
                'accepted_at': timezone.now(),
            }
        )

        invite.used_at = timezone.now()
        invite.save()

        # Return both so the view can log the user in without a second DB hit.
        return client_coordinator, user


# ==============================================
# Scheduling Forms
# ==============================================

class ScheduleForm(forms.Form):
    """
    Form for a client to create or edit a draft Schedule.
    Caregiver is chosen from the client's active matches.
    Support person is chosen from the client's active coordinators (optional).
    """
    caregiver = forms.ModelChoiceField(
        queryset=None,  # set in __init__
        label="Careworker",
        help_text="Select the careworker from one of your active matches",
    )
    support_person = forms.ModelChoiceField(
        queryset=None,  # set in __init__
        required=False,
        label="Support Person",
        help_text="Optionally select a support person to co-approve this schedule",
    )
    match = forms.ModelChoiceField(
        queryset=None,  # set in __init__
        required=False,
        label="Linked Match",
        help_text="Select the active match this schedule is for",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Notes",
        help_text="Optional notes or context for this schedule",
    )

    def __init__(self, *args, client_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import CaregiverProfile, SupportCoordinatorProfile, ClientCoordinator
        from matching.models import Match

        if client_profile is not None:
            # Active matches for this client
            active_matches = Match.objects.filter(
                client=client_profile,
                status="active",
            ).select_related("caregiver__user_profile")

            caregiver_ids = active_matches.values_list("caregiver_id", flat=True)
            self.fields["caregiver"].queryset = CaregiverProfile.objects.filter(
                id__in=caregiver_ids
            ).select_related("user_profile")
            self.fields["caregiver"].label_from_instance = (
                lambda obj: obj.user_profile.display_name
            )

            # Active coordinators for this client
            active_coordinator_ids = ClientCoordinator.objects.filter(
                client_profile=client_profile,
                status="active",
            ).values_list("coordinator_profile_id", flat=True)

            self.fields["support_person"].queryset = SupportCoordinatorProfile.objects.filter(
                id__in=active_coordinator_ids
            ).select_related("user_profile")
            self.fields["support_person"].label_from_instance = (
                lambda obj: obj.user_profile.display_name
            )

            # Active matches as FK link
            self.fields["match"].queryset = active_matches
            self.fields["match"].label_from_instance = (
                lambda obj: f"Match with {obj.caregiver.user_profile.display_name}"
            )
        else:
            from .models import CaregiverProfile, SupportCoordinatorProfile
            self.fields["caregiver"].queryset = CaregiverProfile.objects.none()
            self.fields["support_person"].queryset = SupportCoordinatorProfile.objects.none()
            self.fields["match"].queryset = __import__(
                "matching.models", fromlist=["Match"]
            ).Match.objects.none()

        apply_bulma_classes(self)


class ScheduleEntryForm(forms.Form):
    """
    Form for a single day/time entry in a schedule.
    Used inside a formset.
    """
    from registry.models import DAY_OF_WEEK_CHOICES  # imported at class scope for choices

    day_of_week = forms.ChoiceField(
        choices=[("", "— Select day —")] + [
            ("monday", "Monday"), ("tuesday", "Tuesday"),
            ("wednesday", "Wednesday"), ("thursday", "Thursday"),
            ("friday", "Friday"), ("saturday", "Saturday"), ("sunday", "Sunday"),
        ],
        label="Day",
    )
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}),
        label="Start Time",
    )
    end_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}),
        label="End Time",
    )
    DELETE = forms.BooleanField(required=False, label="Remove this entry")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bulma_classes(self)

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_time")
        end = cleaned_data.get("end_time")
        if start and end and end <= start:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned_data


class ScheduleEntryReviewForm(forms.Form):
    """
    Minimal form for a caregiver or support person to add a rejection note.
    The action (approve/reject) is determined by the URL, not this form.
    """
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        label="Optional note or reason",
        help_text="You may leave a short note explaining your decision.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bulma_classes(self)
