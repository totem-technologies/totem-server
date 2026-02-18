from typing import TYPE_CHECKING, Any, Mapping

from django.contrib.auth.models import BaseUserManager

if TYPE_CHECKING:
    from totem.users.models import User


class TotemUserManager(BaseUserManager):
    """Custom manager for an email-only User model (no username)."""

    @classmethod
    def normalize_email(cls, email: str | None) -> str:
        email = super().normalize_email(email)
        return email.lower()

    def _create_user(self, email: str, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_unusable_password()
        user.save()
        return user

    def create_user(self, email: str, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, **extra_fields)

    def create_superuser(self, email: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, **extra_fields)

    def get_or_create(self, defaults: Mapping[str, Any] | None = None, **kwargs) -> tuple["User", bool]:
        if "email" in kwargs:
            kwargs["email"] = self.normalize_email(kwargs["email"])
        user, created = super().get_or_create(defaults=defaults, **kwargs)
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user, created
