from django import forms
from organizations.models import Organization
from .models import (
    Caregiver,
    Client,
    CONTACT_PREFERENCES,
    TRANSPORTATION_CHOICES,
    EXPERIENCE_CHOICES,
    LANGUAGE_CHOICES,
    PATHOGEN_PROTOCOL_CHOICES,
    ATTENDANT_PROGRAM_CHOICES,
    CARE_NEEDS_CHOICES,
)


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


class CaregiverApplicationForm(AvailabilityMixin, forms.ModelForm):
    contact_preferences = forms.MultipleChoiceField(
        choices=CONTACT_PREFERENCES,
        widget=forms.CheckboxSelectMultiple
    )

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

    class Meta:
        model = Caregiver
        fields = [
            "organization",
            "name",
            "phone",
            "email",
            "contact_preferences",
            "pronouns",
            "base_zip_code",
            "willing_to_work_cities",
            "transportation",
            "hours_looking_for",
            "certified_ihss_worker",
            "additional_certifications",
            "experience_with",
            "languages_spoken",
            "pathogen_protocols",
            "rate",
            "bio",
            "availability_confirmation_agreement",
            "wants_training_updates",
            "other_ways_find_work",
            "helpful_for_finding_work",
            "release_of_liability",
            "signed_date",
        ]

        widgets = {
            "signed_date": forms.DateInput(attrs={"type": "date"}),
            "bio": forms.Textarea(attrs={"rows": 4}),
            "additional_certifications": forms.Textarea(attrs={"rows": 3}),
        }

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

    def save(self, commit=True):
        caregiver = super().save(commit=False)
        caregiver.availability = self.build_availability_json()

        if commit:
            caregiver.save()

        return caregiver


class ClientApplicationForm(AvailabilityMixin, forms.ModelForm):
    contact_preferences = forms.MultipleChoiceField(
        choices=CONTACT_PREFERENCES,
        widget=forms.CheckboxSelectMultiple
    )

    attendant_care_programs = forms.MultipleChoiceField(
        choices=ATTENDANT_PROGRAM_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    care_needs = forms.MultipleChoiceField(
        choices=CARE_NEEDS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    languages_preferred = forms.MultipleChoiceField(
        choices=LANGUAGE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    pathogen_protocol_preferences = forms.MultipleChoiceField(
        choices=PATHOGEN_PROTOCOL_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = Client
        fields = [
            "organization",
            "name",
            "phone",
            "email",
            "contact_preferences",
            "pronouns",
            "address",
            "base_zip_code",
            "attendant_care_programs",
            "languages_preferred",
            "schedule_flexibility",
            "hours_per_week",
            "care_needs",
            "additional_care_needs",
            "preferences",
            "pathogen_protocol_preferences",
        ]

        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "additional_care_needs": forms.Textarea(attrs={"rows": 3}),
            "preferences": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_availability_fields()
        apply_bulma_classes(self)

    def save(self, commit=True):
        client = super().save(commit=False)
        client.availability = self.build_availability_json()

        if commit:
            client.save()

        return client