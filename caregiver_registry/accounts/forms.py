from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm


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
    """

    def confirm_login_allowed(self, user):
        """
        Override to provide a context-aware error message.
        Django's default raises a generic 'inactive' message; we swap that
        for an approval-pending message so users understand what's happening.
        We only reach this method when the password is already verified,
        so showing this message does not leak account existence.
        """
        if not user.is_active:
            raise forms.ValidationError(
                "Your account is pending approval. Once an organization approves "
                "your application you'll receive an email and can log in.",
                code="approval_pending",
            )
