import time
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db.models import BooleanField, CharField, EmailField, TextChoices, UUIDField
from django.urls import reverse
from django.utils.html import escape as html_escape
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from imagekit import ImageSpec
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from timezone_field import TimeZoneField

from totem.email.utils import validate_email_blocked
from totem.users.managers import UserManager
from totem.utils.hash import basic_hash
from totem.utils.models import SluggedModel

from . import analytics


class ProfileImageSpec(ImageSpec):
    processors = [ResizeToFill(400, 400)]
    format = "JPEG"
    options = {"quality": 80, "optimize": True}


def upload_to_id_image(instance, filename: str):
    extension = filename.split(".")[-1]
    epoch_time = int(time.time())
    new_filename = basic_hash(f"{filename}-{epoch_time}")
    user_slug = instance.slug
    return f"profiles/{user_slug}/{new_filename}.{extension}"


class User(SluggedModel, AbstractUser):
    """
    Default custom user model for Totem.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    class ProfileChoices(TextChoices):
        TIEDYE = "TD", _("Tie Dye")
        IMAGE = "IM", _("Image")

    # First and last name do not cover name patterns around the globe
    objects: UserManager = UserManager()
    name = CharField(_("Name"), blank=True, max_length=255)
    first_name = None  # type: ignore
    last_name = None  # type: ignore
    email = EmailField(_("email address"), unique=True, validators=[validate_email_blocked])
    username = None  # type: ignore
    api_key = UUIDField(_("API Key"), db_index=True, default=uuid.uuid4)
    ics_key = UUIDField(_("API Key"), db_index=True, default=uuid.uuid4)
    profile_image = ProcessedImageField(
        blank=True,
        null=True,
        upload_to=upload_to_id_image,
        spec=ProfileImageSpec,  # type: ignore
        help_text="Profile image, must be under 5mb. Will be cropped to a square.",
    )
    profile_avatar_seed = UUIDField(default=uuid.uuid4)
    profile_avatar_type = CharField(
        default=ProfileChoices.TIEDYE,
        max_length=2,
        choices=ProfileChoices.choices,
    )
    verified = BooleanField(_("Verified"), default=False)
    timezone = TimeZoneField(choices_display="WITH_GMT_OFFSET")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"slug": self.slug})

    def get_login_url(self, after_login_url: str | None, mobile: bool = False) -> str:
        from sesame.utils import get_query_string

        if not after_login_url or after_login_url.startswith("http"):
            after_login_url = reverse("users:redirect")

        url = reverse("magic-login")

        url += get_query_string(self)
        url += "&next=" + after_login_url
        return url

    def get_keeper_url(self):
        # hack until we can connect keepers to user profiles
        keepers = {
            "bo@totem.org": reverse("pages:about"),
            "admin@admin.com": reverse("pages:about"),
            "heather@totem.org": reverse("pages:keepers", kwargs={"name": "heather"}),
            "vanessa@totem.org": reverse("pages:keepers", kwargs={"name": "vanessa"}),
            "gabe@totem.org": reverse("pages:keepers", kwargs={"name": "gabe"}),
        }
        return keepers.get(self.email, reverse("users:detail", kwargs={"slug": self.slug}))

    def get_admin_url(self):
        return reverse(f"admin:{self._meta.app_label}_{self._meta.model_name}_change", args=(self.pk,))

    def identify(self):
        analytics.identify_user(self)

    def analytics_id(self):
        return settings.ENVIRONMENT_NAME.lower() + "_" + str(self.pk)

    def randomize_avatar(self):
        self.profile_avatar_seed = uuid.uuid4()
        self.save()

    def __str__(self):
        return f"<User: {self.name}, slug: {self.slug}, email: {self.email}>"

    def clean(self):
        super().clean()
        self.email = strip_tags(self.__class__.objects.normalize_email(self.email))
        self.name = html_escape(strip_tags(self.name.strip()))
