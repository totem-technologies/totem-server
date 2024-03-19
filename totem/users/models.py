import time
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import BooleanField, CharField, EmailField, TextChoices, URLField, UUIDField
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.utils.html import escape as html_escape
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from imagekit import ImageSpec
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from timezone_field import TimeZoneField

from totem.email.utils import validate_email_blocked
from totem.users.managers import UserManager
from totem.utils.fields import MaxLengthTextField
from totem.utils.hash import basic_hash
from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import AdminURLMixin, SluggedModel

from . import analytics

if TYPE_CHECKING:
    from django.db.models.query import QuerySet

    from totem.circles.models import Circle, CircleEvent
    from totem.onboard.models import OnboardModel


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


class User(AdminURLMixin, SluggedModel, AbstractUser):
    """
    Default custom user model for Totem.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # Related Types
    onboard: "OnboardModel"
    events_attending: "QuerySet[CircleEvent]"
    events_joined: "QuerySet[CircleEvent]"
    created_circles: "QuerySet[Circle]"
    keeper_profile: "KeeperProfile"

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
        if self.keeper_profile.username:
            return reverse("profiles", kwargs={"name": self.keeper_profile.username})
        return reverse("users:detail", kwargs={"slug": self.slug})

    def is_keeper(self):
        return hasattr(self, "keeper_profile")

    def month_joined(self):
        return self.date_created.strftime("%B %Y")

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


class KeeperProfile(AdminURLMixin, models.Model, MarkdownMixin):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="keeper_profile")
    username = CharField(
        max_length=30, unique=True, db_index=True, blank=True, null=True, help_text="Your unique username."
    )
    title = CharField(max_length=255, default="Keeper")
    bio = MarkdownField(blank=True)
    location = CharField(max_length=255, default="Earth", help_text="Where are you located? (City, State, Country)")
    languages = CharField(
        max_length=255, default="English", help_text="What languages do you speak? (English, Spanish, etc.)"
    )
    instagram_username = CharField(max_length=255, blank=True, help_text="Your Instagram username, no @ symbol")
    x_username = CharField(max_length=255, blank=True, help_text="Your X username, no @ symbol")
    website = URLField(max_length=255, blank=True, help_text="Your personal website.")

    def __str__(self):
        return f"<KeeperProfile: {self.user.name}, email: {self.user.email}>"

    def get_absolute_url(self):
        return self.user.get_absolute_url()

    def clean(self):
        # make sure username is saved lowercase and only contains letters, numbers, and underscores and that it doesn't resolve to a real URL
        if self.username:
            self.username = self.username.lower()
            self.username = "".join(e for e in self.username if e.isalnum() or e == "_")
            if len(self.username) < 2:
                raise ValidationError(_("Username must be at least 2 characters long."))
            try:
                if resolve(f"/{self.username}/").url_name != "profiles":
                    raise ValidationError(_("Username is already taken."))
            except Resolver404:
                pass

        super().clean()


class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="feedback", null=True)
    email = EmailField(_("Email Address"), null=True, blank=True)
    message = MaxLengthTextField(null=False, max_length=10000, blank=False, verbose_name=_("Feedback"))
    date_created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"<Feedback: {self.date_created}>"


def default_expires_at() -> datetime:
    return timezone.now() + timedelta(days=7)


class ActionToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    action = models.CharField(max_length=100)
    parameters = models.JSONField(default=dict)
    expires_at = models.DateTimeField(default=default_expires_at)

    def is_valid(self) -> bool:
        return timezone.now() < self.expires_at

    @classmethod
    def cleanup(cls):
        cls.objects.filter(expires_at__lt=timezone.now()).delete()
