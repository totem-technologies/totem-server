from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import User


def validate_registration_email(email: str) -> str:
    """Restrict new staging accounts while allowing existing users to log in."""
    # Use the configured host so alternate request hosts cannot bypass the policy.
    if settings.SITE_HOST.lower().split(":", 1)[0] != "totem.kbl.io":
        return email
    normalized_email = User.objects.normalize_email(email)
    if normalized_email.endswith("@totem.org") or User.objects.filter(email=normalized_email).exists():
        return email
    raise ValidationError(
        _(
            "This is Totem's staging server. Account creation is limited to @totem.org email addresses. "
            "Please go to https://totem.org to create your account."
        ),
        code="staging_signup_restricted",
    )
