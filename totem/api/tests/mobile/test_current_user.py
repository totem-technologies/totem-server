from datetime import timedelta

from django.test import Client
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken

from totem.api.oauth import create_oauth_tokens
from totem.users.tests.factories import UserFactory


class TestProtectedMobileEndpoint:
    """Test the protected mobile API endpoints."""

    def test_current_user_with_valid_token(self, client: Client, db, auth_user, auth_token):
        """Test accessing the currentuser endpoint with a valid token."""
        auth_header = f"Bearer {auth_token}"

        response = client.get(reverse("mobile-api:user_current"), HTTP_AUTHORIZATION=auth_header)

        # Check response
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == auth_user.email
        assert data["name"] == str(auth_user.name)

    def test_current_user_without_token(self, client: Client, db):
        """Test accessing the currentuser endpoint without a token."""
        response = client.get(reverse("mobile-api:user_current"))

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_current_user_with_invalid_token(self, client: Client, db):
        """Test accessing the currentuser endpoint with an invalid token."""
        auth_header = "Bearer invalid.token.here"

        response = client.get(reverse("mobile-api:user_current"), HTTP_AUTHORIZATION=auth_header)

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_current_user_with_expired_token(self, client: Client, db, auth_user, oauth_app):
        """Test accessing the currentuser endpoint with an expired token."""
        expired_token = AccessToken.objects.create(
            user=auth_user,
            application=oauth_app,
            token="expired-test-token",
            expires=timezone.now() - timedelta(minutes=5),
            scope="read write",
        )

        auth_header = f"Bearer {expired_token.token}"

        response = client.get(reverse("mobile-api:user_current"), HTTP_AUTHORIZATION=auth_header)

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_current_user_with_deactivated_user(self, client: Client, db, auth_user, auth_token):
        """Test accessing the currentuser endpoint with a deactivated user."""
        # Deactivate the user
        auth_user.is_active = False
        auth_user.save()

        auth_header = f"Bearer {auth_token}"

        response = client.get(reverse("mobile-api:user_current"), HTTP_AUTHORIZATION=auth_header)

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_current_user_with_nonexistent_user(self, client: Client, db, oauth_app):
        """Test accessing the currentuser endpoint with a token for a deleted user."""
        # Create a user and get a token
        temp_user = UserFactory()
        tokens = create_oauth_tokens(temp_user)

        # Delete the user
        temp_user.delete()

        auth_header = f"Bearer {tokens.access_token}"

        response = client.get(reverse("mobile-api:user_current"), HTTP_AUTHORIZATION=auth_header)

        # Should return 401 Unauthorized
        assert response.status_code == 401
