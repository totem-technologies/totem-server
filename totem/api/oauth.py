from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja.security import HttpBearer
from oauthlib.common import generate_token
from oauth2_provider.models import AccessToken, Application
from oauth2_provider.models import RefreshToken as OAuthRefreshToken

from totem.users.models import User


class TokenResponse:
    def __init__(self, access_token: str, refresh_token: str, expires_in: int):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in


def get_mobile_application() -> Application:
    return Application.objects.get(name="Totem Mobile")


def create_oauth_tokens(user: User, application: Application | None = None) -> TokenResponse:
    """Create a new DOT access token and refresh token for a user."""
    if application is None:
        application = get_mobile_application()

    expires_in = settings.OAUTH2_PROVIDER["ACCESS_TOKEN_EXPIRE_SECONDS"]
    expires = timezone.now() + timedelta(seconds=expires_in)

    access_token = AccessToken.objects.create(
        user=user,
        application=application,
        token=generate_token(),
        expires=expires,
        scope="read write",
    )

    refresh_token = OAuthRefreshToken.objects.create(
        user=user,
        application=application,
        token=generate_token(),
        access_token=access_token,
    )

    return TokenResponse(
        access_token=access_token.token,
        refresh_token=refresh_token.token,
        expires_in=expires_in,
    )


class OAuth2TokenAuth(HttpBearer):
    """Django-ninja auth class that validates DOT access tokens."""

    def authenticate(self, request: HttpRequest, token: str) -> User | None:
        try:
            access_token = AccessToken.objects.select_related("user").get(token=token)
        except AccessToken.DoesNotExist:
            return None

        if access_token.is_expired():
            return None

        user = access_token.user
        if not user or not user.is_active:
            return None

        request.user = user
        return user


class DualAuth(HttpBearer):
    """Transitional auth class that accepts both DOT and legacy JWT tokens."""

    def authenticate(self, request: HttpRequest, token: str) -> User | None:
        # Try DOT token first
        user = OAuth2TokenAuth().authenticate(request, token)
        if user is not None:
            return user

        # Fall back to legacy JWT
        from totem.api.mobile_api import JWTAuth

        return JWTAuth().authenticate(request, token)
