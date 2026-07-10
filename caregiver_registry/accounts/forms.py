from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction


User = get_user_model()


# ==============================================
# Organization Admin Signup Form
# ==============================================

class OrganizationAdminSignupForm(forms.Form):
    # Organization fields
    organization_name = forms.CharField(max_length=255, label="Organization Name")
    organization_city = forms.CharField(max_length=100, label="City")
    organization_zip_code = forms.CharField(max_length=10, label="ZIP Code", required=False)
    organization_contact_email = forms.EmailField(label="Organization Contact Email", required=False)

    # Admin user fields
    first_name = forms.CharField(max_length=150, label="First Name")
    last_name = forms.CharField(max_length=150, label="Last Name")
    username = forms.CharField(max_length=150, label="Username")
    email = forms.EmailField(label="Email")
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("That email is already in use.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        return password2

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
        )
        return user


# ==============================================
# Custom Login Form
# ==============================================

class CareWebLoginForm(AuthenticationForm):
    """
    Custom login form that shows a friendlier 'approval pending' message
    when a user's credentials are correct but their account is inactive.

    Django's ModelBackend returns None for inactive users (is_active=False),
    so confirm_login_allowed() is never called for them via the normal flow.
    We override clean() to intercept this case explicitly before the generic
    "incorrect credentials" error is raised.
    """

    def clean(self):
        """
        Before delegating to AuthenticationForm.clean(), check whether the
        supplied credentials belong to an *inactive* user.  If so, raise the
        friendlier 'approval pending' message instead of the generic error.
        We do NOT reveal whether the account exists when the password is wrong.
        """
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user_obj = User._default_manager.get_by_natural_key(username)
                if not user_obj.is_active and user_obj.check_password(password):
                    raise forms.ValidationError(
                        "Your account is pending approval. Once an organization approves "
                        "your application you'll receive an email and can log in.",
                        code="approval_pending",
                    )
            except User.DoesNotExist:
                pass  # let super().clean() raise the generic invalid-login error

        return super().clean()

    def confirm_login_allowed(self, user):
        """
        Fallback guard — called by super().clean() when authentication
        succeeds via a non-ModelBackend that may allow inactive users.
        """
        if not user.is_active:
            raise forms.ValidationError(
                "Your account is pending approval. Once an organization approves "
                "your application you'll receive an email and can log in.",
                code="approval_pending",
            )


# ==============================================
# Staff Invite Form (sent by org admin/staff)
# ==============================================

STAFF_ROLE_CHOICES = [
    ("staff", "Staff"),
    ("admin", "Admin"),
]

CONTACT_PREFERENCES = [
    ("phone", "Phone"),
    ("email", "Email"),
    ("text", "Text Message"),
    ("any", "Any"),
]

PRONOUN_CHOICES = [
    ("she_her", "She/Her"),
    ("he_him", "He/Him"),
    ("they_them", "They/Them"),
    ("she_they", "She/They"),
    ("he_they", "He/They"),
    ("ze_zir", "Ze/Zir"),
    ("ask_me", "Ask Me"),
    ("self_describe", "Self Describe"),
]


class StaffInviteForm(forms.Form):
    """
    Form for an org admin/staff to invite a new staff member.
    Creates an OrganizationStaffInvite with a unique token link.
    """
    email = forms.EmailField(
        label="Staff Email",
        help_text="Email address of the person you want to invite as staff."
    )
    role = forms.ChoiceField(
        choices=STAFF_ROLE_CHOICES,
        label="Role",
        initial="staff",
        help_text="Select the role for the invited staff member.",
    )
    can_approve_applications = forms.BooleanField(
        required=False,
        label="Can approve caregiver/client applications",
    )
    can_invite_staff = forms.BooleanField(
        required=False,
        label="Can invite additional staff",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            field.widget.attrs["class"] = "input"
        self.fields["role"].widget.attrs["class"] = "input"


# ==============================================
# Staff Signup Form (accepted by invited staff)
# ==============================================

class StaffSignupForm(forms.Form):
    """
    Form for an invited staff member to accept the invitation and create
    their account.  Creates/updates User, UserProfile, StaffProfile, and
    OrganizationStaff records.
    """
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"readonly": "readonly"}),
    )
    first_name = forms.CharField(max_length=150, label="First Name")
    last_name = forms.CharField(max_length=150, label="Last Name")
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        help_text="Choose a secure password you'll use to log in.",
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
        help_text="Enter the same password again to confirm.",
    )
    phone = forms.CharField(max_length=25, label="Phone Number", required=False)
    contact_preferences = forms.MultipleChoiceField(
        choices=CONTACT_PREFERENCES,
        widget=forms.CheckboxSelectMultiple,
        label="Preferred Contact Methods",
        required=False,
    )
    pronouns = forms.ChoiceField(
        choices=[("", "— Select —")] + PRONOUN_CHOICES,
        required=False,
        label="Pronouns",
    )
    title = forms.CharField(
        max_length=150,
        required=False,
        label="Job Title",
        help_text="E.g., Case Manager, Care Coordinator, Administrator, etc.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxSelectMultiple, forms.CheckboxInput)):
                continue
            field.widget.attrs["class"] = "input"

    def clean(self):
        cleaned_data = super().clean()
        pw1 = cleaned_data.get("password1")
        pw2 = cleaned_data.get("password2")
        if pw1 and pw2 and pw1 != pw2:
            raise forms.ValidationError("The two password fields must match.")
        return cleaned_data

    @transaction.atomic
    def save(self, invite):
        """
        Create or update User/UserProfile/StaffProfile/OrganizationStaff,
        mark the invite as accepted, and return the (org_staff, user) tuple.
        """
        from accounts.models import UserProfile, StaffProfile
        from organizations.models import OrganizationStaff
        from django.utils import timezone

        email = self.cleaned_data["email"].lower()

        # Create or get the auth user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": self.cleaned_data["first_name"],
                "last_name": self.cleaned_data["last_name"],
            },
        )
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.set_password(self.cleaned_data["password1"])
        user.is_active = True
        user.save()

        # Create or update UserProfile
        user_profile, _ = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "phone": self.cleaned_data.get("phone", ""),
                "pronouns": self.cleaned_data.get("pronouns", ""),
                "contact_preferences": self.cleaned_data.get("contact_preferences") or [],
            },
        )

        # Create or update StaffProfile
        staff_profile, _ = StaffProfile.objects.update_or_create(
            user_profile=user_profile,
            defaults={
                "title": self.cleaned_data.get("title", ""),
            },
        )

        # Create OrganizationStaff relationship
        is_admin = invite.role == "admin"
        org_staff, _ = OrganizationStaff.objects.update_or_create(
            organization=invite.organization,
            staff_profile=staff_profile,
            defaults={
                "role": invite.role,
                "status": "active",
                "can_view_dashboard": True,
                "can_approve_applications": invite.can_approve_applications,
                "can_invite_staff": invite.can_invite_staff or is_admin,
                "invited_by": invite.invited_by if hasattr(invite, "invited_by") else None,
                "accepted_at": timezone.now(),
            },
        )

        # Mark invite as accepted
        invite.accepted = True
        invite.save()

        return org_staff, user
