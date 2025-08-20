from allauth.account.forms import SignupForm as AllauthSignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django.contrib.auth import forms as admin_forms
from django.contrib.auth import get_user_model
from django.forms import BooleanField, CharField, EmailField, Form, HiddenInput
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from totem.email.utils import validate_email_blocked

User = get_user_model()


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):  # type: ignore
        model = User
        field_classes = {"email": EmailField}


class UserAdminCreationForm(admin_forms.UserCreationForm):
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):  # type: ignore
        model = User
        fields = ("email",)
        field_classes = {"email": EmailField}
        error_messages = {
            "email": {"unique": _("This email has already been taken.")},
        }


class UserSignupForm(AllauthSignupForm):
    """
    Form that will be rendered on a user sign up section/screen.
    Default fields will be added automatically.
    Check UserSocialSignupForm for accounts created from social.
    """


class UserSocialSignupForm(SocialSignupForm):
    """
    Renders the form when user has signed up using social accounts.
    Default fields will be added automatically.
    See UserSignupForm otherwise.
    """


class LoginForm(Form):
    form_url = reverse_lazy("users:login")
    email = EmailField(validators=[validate_email_blocked])
    # Honeypot field - should remain empty
    website = CharField(
        required=False,
        label="",  # Empty string for label
        template_name="fields/honeypot.html",  # type: ignore # Custom template to hide the field
    )
    # after_login_url removed, only 'next' is supported
    success_url = CharField(required=False, widget=HiddenInput())


class SignupForm(LoginForm):
    newsletter_consent = BooleanField(
        required=False,
        label=_("Yes, receive email updates (optional)"),
        template_name="fields/checkbox.html",  # type: ignore
    )
