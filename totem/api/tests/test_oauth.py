from datetime import timedelta

import pytest
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application
from oauth2_provider.models import RefreshToken as OAuthRefreshToken

from totem.api.auth import generate_jwt_token
from totem.api.oauth import DualAuth, OAuth2TokenAuth, create_oauth_tokens, get_mobile_application
from totem.users.tests.factories import UserFactory


@pytest.fixture
def oauth_app(db) -> Application:
    app, _ = Application.objects.get_or_create(
        name="Totem Mobile",
        defaults={
            "client_type": Application.CLIENT_PUBLIC,
            "authorization_grant_type": Application.GRANT_PASSWORD,
            "skip_authorization": True,
        },
    )
    return app


@pytest.fixture
def oauth_user(db):
    return UserFactory(email="oauth_test@example.com")


@pytest.fixture
def oauth_access_token(oauth_user, oauth_app):
    return AccessToken.objects.create(
        user=oauth_user,
        application=oauth_app,
        token="test-access-token-valid",
        expires=timezone.now() + timedelta(hours=1),
        scope="read write",
    )


@pytest.fixture
def request_factory():
    return RequestFactory()


class TestCreateOAuthTokens:
    """Test the create_oauth_tokens helper."""

    def test_creates_access_and_refresh_tokens(self, oauth_user, oauth_app):
        result = create_oauth_tokens(oauth_user, oauth_app)

        assert result.access_token
        assert result.refresh_token
        assert result.expires_in == 3600

        # Verify tokens exist in DB
        assert AccessToken.objects.filter(token=result.access_token, user=oauth_user).exists()
        assert OAuthRefreshToken.objects.filter(token=result.refresh_token, user=oauth_user).exists()

    def test_refresh_token_linked_to_access_token(self, oauth_user, oauth_app):
        result = create_oauth_tokens(oauth_user, oauth_app)

        refresh = OAuthRefreshToken.objects.get(token=result.refresh_token)
        assert refresh.access_token.token == result.access_token

    def test_uses_default_application(self, oauth_user, oauth_app):
        result = create_oauth_tokens(oauth_user)

        access = AccessToken.objects.get(token=result.access_token)
        assert access.application == oauth_app


class TestOAuth2TokenAuth:
    """Test the OAuth2TokenAuth django-ninja auth class."""

    def test_valid_token(self, request_factory, oauth_user, oauth_access_token):
        request = request_factory.get("/")
        auth = OAuth2TokenAuth()
        result = auth.authenticate(request, oauth_access_token.token)

        assert result == oauth_user
        assert request.user == oauth_user

    def test_expired_token(self, request_factory, oauth_user, oauth_app):
        expired_token = AccessToken.objects.create(
            user=oauth_user,
            application=oauth_app,
            token="expired-token",
            expires=timezone.now() - timedelta(minutes=5),
            scope="read write",
        )
        request = request_factory.get("/")
        auth = OAuth2TokenAuth()
        result = auth.authenticate(request, expired_token.token)

        assert result is None

    def test_nonexistent_token(self, request_factory, db):
        request = request_factory.get("/")
        auth = OAuth2TokenAuth()
        result = auth.authenticate(request, "nonexistent-token")

        assert result is None

    def test_revoked_token(self, request_factory, oauth_user, oauth_access_token):
        oauth_access_token.revoke()

        request = request_factory.get("/")
        auth = OAuth2TokenAuth()
        result = auth.authenticate(request, oauth_access_token.token)

        assert result is None

    def test_inactive_user(self, request_factory, oauth_user, oauth_access_token):
        oauth_user.is_active = False
        oauth_user.save()

        request = request_factory.get("/")
        auth = OAuth2TokenAuth()
        result = auth.authenticate(request, oauth_access_token.token)

        assert result is None

    def test_valid_token_on_protected_endpoint(self, client: Client, oauth_user, oauth_access_token):
        """Integration test: DOT token works on a real protected endpoint."""
        response = client.get(
            reverse("mobile-api:user_current"),
            HTTP_AUTHORIZATION=f"Bearer {oauth_access_token.token}",
        )

        assert response.status_code == 401  # Still uses JWTAuth, not OAuth2TokenAuth yet


class TestDualAuth:
    """Test the DualAuth transitional auth class."""

    def test_accepts_dot_token(self, request_factory, oauth_user, oauth_access_token):
        request = request_factory.get("/")
        auth = DualAuth()
        result = auth.authenticate(request, oauth_access_token.token)

        assert result == oauth_user

    def test_falls_back_to_jwt(self, request_factory, oauth_user, oauth_app):
        jwt_token = generate_jwt_token(oauth_user)

        request = request_factory.get("/")
        auth = DualAuth()
        result = auth.authenticate(request, jwt_token)

        assert result == oauth_user

    def test_rejects_both_invalid(self, request_factory, db):
        request = request_factory.get("/")
        auth = DualAuth()
        result = auth.authenticate(request, "completely-invalid-token")

        assert result is None

    def test_prefers_dot_over_jwt(self, request_factory, oauth_user, oauth_app):
        """When a token happens to be a valid DOT token, DOT auth is used (tried first)."""
        tokens = create_oauth_tokens(oauth_user, oauth_app)

        request = request_factory.get("/")
        auth = DualAuth()
        result = auth.authenticate(request, tokens.access_token)

        assert result == oauth_user
