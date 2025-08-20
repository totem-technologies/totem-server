import secrets
import time
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import BooleanField, CharField, EmailField, TextChoices, URLField, UUIDField
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from imagekit import ImageSpec
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from timezone_field import TimeZoneField

from totem.email.utils import validate_email_blocked
from totem.users.managers import TotemUserManager as UserManager
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

    objects: UserManager = UserManager()  # type: ignore
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
    name = CharField(_("Name"), blank=True, max_length=255)
    first_name = None  # type: ignore
    last_name = None  # type: ignore
    email = EmailField(_("email address"), unique=True, validators=[validate_email_blocked])
    username = None  # type: ignore
    api_key = UUIDField(_("API Key"), db_index=True, default=uuid.uuid4, unique=True)
    ics_key = UUIDField(_("ICS Key"), db_index=True, default=uuid.uuid4)
    newsletter_consent = BooleanField(_("Receive updates from Totem"), default=False)
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
    timezone = TimeZoneField(choices_display="WITH_GMT_OFFSET", blank=True)
    fixed_pin = CharField(
        _("Fixed PIN"),
        max_length=6,
        blank=True,
        default="",
        help_text="Fixed PIN for app store review access. Must be enabled to work.",
    )
    fixed_pin_enabled = BooleanField(
        _("Fixed PIN Enabled"),
        default=False,
        help_text="Enable fixed PIN login for app store reviews. Not allowed for staff users.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"slug": self.slug})

    def get_keeper_url(self):
        if hasattr(self, "keeper_profile") and self.keeper_profile.username:
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
        self.name = strip_tags(self.name.strip())

        # Prevent staff users from enabling fixed pin
        if self.fixed_pin_enabled and self.is_staff:
            raise ValidationError(_("Fixed PIN login is not allowed for staff users."))


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
    return timezone.now() + timedelta(days=14)


def default_pin_expires_at() -> datetime:
    return timezone.now() + timedelta(minutes=15)


class LoginPinManager(models.Manager):
    def generate_pin(self, user: User) -> "LoginPin":
        """Generate a new PIN for a user, invalidating any existing PINs."""
        # Generate a secure 6-digit PIN using the secrets module
        pin = "".join(secrets.choice("0123456789") for _ in range(6))

        # Delete any existing PINs for this user and create new one
        self.filter(user=user).delete()
        return self.create(user=user, pin=pin)

    def validate_pin(self, user: User, pin: str) -> tuple[bool, "LoginPin | None"]:
        """
        Validate a PIN for a user. Returns (is_valid, pin_obj).
        PIN object is returned even if invalid to allow for attempt counting.
        Supports fixed PIN as fallback for app store reviews.
        """
        try:
            pin_obj = self.get(user=user, expires_at__gt=timezone.now())
            is_valid = pin_obj.is_valid() and pin_obj.pin == pin
            if is_valid:
                # Valid PIN - mark as used
                pin_obj.used = True
                pin_obj.save()
                return True, pin_obj
            else:
                # Regular PIN didn't match - check fixed PIN as fallback
                if self._validate_fixed_pin(user, pin):
                    return True, None
                # Neither regular nor fixed PIN matched - increment failed attempts
                pin_obj.increment_failed_attempts()
                return False, pin_obj
        except self.model.DoesNotExist:
            if self._validate_fixed_pin(user, pin):
                return True, None
            return False, None

    def _validate_fixed_pin(self, user: User, pin: str) -> bool:
        return not user.is_staff and user.fixed_pin_enabled and user.fixed_pin and user.fixed_pin == pin


class LoginPin(models.Model):
    MAX_ATTEMPTS = 10
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    pin = models.CharField(max_length=6)
    expires_at = models.DateTimeField(default=default_pin_expires_at)
    used = models.BooleanField(default=False)
    failed_attempts = models.IntegerField(default=0)

    objects: LoginPinManager = LoginPinManager()  # type: ignore

    def is_valid(self) -> bool:
        return not self.used and not self.is_expired() and not self.has_too_many_attempts()

    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    def has_too_many_attempts(self) -> bool:
        return self.failed_attempts >= self.MAX_ATTEMPTS

    def increment_failed_attempts(self):
        self.failed_attempts += 1
        self.save()

    @classmethod
    def cleanup(cls):
        """Remove expired PINs."""
        cls.objects.filter(expires_at__lt=timezone.now()).delete()

    class Meta:
        indexes = [
            models.Index(fields=["user", "pin", "expires_at"]),
        ]


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


class RefreshTokenManager(models.Manager):
    def generate_token(self, user) -> tuple[str, "RefreshToken"]:
        """Generate a new refresh token for a user on a specific device."""
        # Generate a random 128-bit token
        token_string = secrets.token_hex(16)  # 16 bytes = 128 bits

        # Hash token for storage
        token_hash = make_password(token_string)

        # Create token in database
        token_obj: RefreshToken = self.create(user=user, token_hash=token_hash)

        # Check if user has too many tokens and remove oldest ones
        MAX_TOKENS_PER_USER = 200  # Max 200 tokens per user
        user_tokens = self.filter(user=user).order_by("-created_at")
        if user_tokens.count() > MAX_TOKENS_PER_USER:
            for token in user_tokens[MAX_TOKENS_PER_USER:]:
                token.delete()

        return token_string, token_obj

    def validate_token(self, token_string):
        """Validate a refresh token. Returns (user, token_obj) if valid."""
        # Need to check all active tokens since we don't know which one matches
        for token in self.filter(is_active=True):
            if check_password(token_string, token.token_hash):
                if not token.is_active:
                    return None, None

                # Update last used timestamp
                token.last_used_at = timezone.now()
                token.save(update_fields=["last_used_at"])
                return token.user, token

        return None, None


class RefreshToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_tokens")
    token_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    objects: RefreshTokenManager = RefreshTokenManager()  # type: ignore

    class Meta:
        indexes = [
            models.Index(fields=["user", "token_hash", "created_at"]),
        ]

    def invalidate(self):
        """Invalidate this token."""
        self.is_active = False
        self.save(update_fields=["is_active"])

    @classmethod
    def invalidate_all_for_user(cls, user):
        """Invalidate all tokens for a user across all devices."""
        cls.objects.filter(user=user).update(is_active=False)
