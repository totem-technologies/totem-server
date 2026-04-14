from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja.security import HttpBearer
from oauthlib.common import generate_token
from oauth2_provider.models import AccessToken, Application
from oauth2_provider.models import RefreshToken as OAuthRefreshToken

from totem.users.models import User


@dataclass
class OAuthTokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def get_mobile_application() -> Application:
    return Application.objects.get(name="Totem Mobile")


@transaction.atomic
def create_oauth_tokens(user: User, application: Application | None = None) -> OAuthTokenPair:
    """Create a new django-oauth-toolkit access token and refresh token for a user."""
    if application is None:
        application = get_mobile_application()

    expires_in: int = settings.OAUTH2_PROVIDER["ACCESS_TOKEN_EXPIRE_SECONDS"]
    expires = timezone.now() + timedelta(seconds=expires_in)

    access_token = AccessToken.objects.create(
        user=user,
        application=application,
        token=generate_token(),
        expires=expires,
        scope="read write",
    )

    OAuthRefreshToken.objects.create(
        user=user,
        application=application,
        token=generate_token(),
        access_token=access_token,
    )

    return OAuthTokenPair(
        access_token=access_token.token,
        refresh_token=access_token.refresh_token.token,
        expires_in=expires_in,
    )


def _get_grace_period_seconds() -> int:
    return settings.OAUTH2_PROVIDER.get("REFRESH_TOKEN_GRACE_PERIOD_SECONDS", 0)


def refresh_oauth_tokens(refresh_token_string: str) -> tuple[OAuthTokenPair | None, User | None]:
    """Validate a refresh token and issue a new token pair. Revokes the old pair.

    Supports a grace period: if the token was recently revoked (e.g., client lost the
    response mid-refresh), returns the already-issued replacement tokens instead of
    creating new ones.

    Returns (OAuthTokenPair, user) on success, (None, None) if token is invalid,
    or (None, user) if the user's account is deactivated.
    """
    with transaction.atomic():
        try:
            old_refresh = (
                OAuthRefreshToken.objects.select_for_update()
                .select_related("user", "application")
                .get(token=refresh_token_string, revoked__isnull=True)
            )
        except OAuthRefreshToken.DoesNotExist:
            # Check if this token was recently revoked (grace period)
            return _handle_grace_period(refresh_token_string)

        user = old_refresh.user
        if not user.is_active:
            old_refresh.revoke()
            return None, user

        application = old_refresh.application

        # Revoke old token pair and issue new tokens
        old_refresh.revoke()
        return create_oauth_tokens(user, application), user


def _handle_grace_period(refresh_token_string: str) -> tuple[OAuthTokenPair | None, User | None]:
    """If a refresh token was revoked within the grace period, return its replacement tokens."""
    grace_seconds = _get_grace_period_seconds()
    if grace_seconds <= 0:
        return None, None

    grace_cutoff = timezone.now() - timedelta(seconds=grace_seconds)
    try:
        old_refresh = OAuthRefreshToken.objects.select_related("user", "application").get(
            token=refresh_token_string, revoked__gte=grace_cutoff
        )
    except OAuthRefreshToken.DoesNotExist:
        return None, None

    user = old_refresh.user
    if not user.is_active:
        return None, user

    # Find the replacement token created when this one was revoked
    replacement = (
        OAuthRefreshToken.objects.select_related("access_token")
        .filter(
            user=user,
            application=old_refresh.application,
            revoked__isnull=True,
            created__gte=old_refresh.revoked,
        )
        .order_by("created")
        .first()
    )
    if not replacement or not replacement.access_token:
        return None, None

    # Compute actual remaining time on the replacement access token
    remaining = (replacement.access_token.expires - timezone.now()).total_seconds()
    expires_in = max(0, int(remaining))

    return OAuthTokenPair(
        access_token=replacement.access_token.token,
        refresh_token=replacement.token,
        expires_in=expires_in,
    ), user


def revoke_oauth_refresh_token(refresh_token_string: str) -> bool:
    """Revoke a refresh token and its associated access token. Returns True if found."""
    try:
        refresh = OAuthRefreshToken.objects.get(token=refresh_token_string, revoked__isnull=True)
        refresh.revoke()
        return True
    except OAuthRefreshToken.DoesNotExist:
        return False


class OAuth2TokenAuth(HttpBearer):
    """Django-ninja auth class that validates django-oauth-toolkit access tokens."""

    def authenticate(self, request: HttpRequest, token: str) -> User | None:
        try:
            access_token = AccessToken.objects.select_related("user").get(token=token)
        except AccessToken.DoesNotExist:
            return None

        if not access_token.is_valid():
            return None

        user = access_token.user
        if not user or not user.is_active:
            return None

        request.user = user
        return user
