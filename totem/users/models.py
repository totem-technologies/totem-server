import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db.models import CharField, EmailField, UUIDField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from totem.email.utils import validate_email_blocked
from totem.users.managers import UserManager

from . import analytics


class User(AbstractUser):
    """
    Default custom user model for Totem.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore
    last_name = None  # type: ignore
    email = EmailField(_("email address"), unique=True, validators=[validate_email_blocked])
    username = None  # type: ignore
    api_key = UUIDField(_("API Key"), db_index=True, default=uuid.uuid4)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.pk})

    def identify(self):
        analytics.identify_user(self)

    def analytics_id(self):
        return settings.ENVIRONMENT_NAME.lower() + "_" + str(self.pk)
