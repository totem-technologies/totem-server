import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db.models import BooleanField, CharField, EmailField, UUIDField
from django.urls import reverse
from django.utils.html import escape as html_escape
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _

from totem.email.utils import validate_email_blocked
from totem.users.managers import UserManager
from totem.utils.models import SluggedModel

from . import analytics


class User(SluggedModel, AbstractUser):
    """
    Default custom user model for Totem.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    objects: UserManager = UserManager()
    name = CharField(_("Name"), blank=True, max_length=255)
    first_name = None  # type: ignore
    last_name = None  # type: ignore
    email = EmailField(_("email address"), unique=True, validators=[validate_email_blocked])
    username = None  # type: ignore
    api_key = UUIDField(_("API Key"), db_index=True, default=uuid.uuid4)
    ics_key = UUIDField(_("API Key"), db_index=True, default=uuid.uuid4)
    profile_image = CharField(max_length=255, null=True, blank=True)
    verified = BooleanField(_("Verified"), default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"slug": self.slug})

    def get_admin_url(self):
        return reverse(f"admin:{self._meta.app_label}_{self._meta.model_name}_change", args=(self.pk,))

    def identify(self):
        analytics.identify_user(self)

    def analytics_id(self):
        return settings.ENVIRONMENT_NAME.lower() + "_" + str(self.pk)

    def __str__(self):
        return f"<User: {self.name}, slug: {self.slug}>"

    def clean(self):
        super().clean()
        self.email = strip_tags(self.__class__.objects.normalize_email(self.email))
        self.name = html_escape(strip_tags(self.name.strip()))
        if self.profile_image:
            self.profile_image = strip_tags(self.profile_image.strip())
