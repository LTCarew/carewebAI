from django import forms

from .models import Caregiver, Client


class CaregiverApplicationForm(forms.ModelForm):
    class Meta:
        model = Caregiver

        fields = [
            "organization",
            "name",
            "email",
            "skills",
            "availability",
            "preferences",
        ]


class ClientApplicationForm(forms.ModelForm):
    class Meta:
        model = Client

        fields = [
            "organization",
            "name",
            "email",
            "care_needs",
            "schedule",
            "preferences",
        ]