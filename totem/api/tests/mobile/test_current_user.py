from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.api.auth import generate_jwt_token
from totem.users.tests.factories import UserFactory


@pytest.fixture
def auth_user():
    """Create a user for testing authentication."""
    return UserFactory(email="auth_test@example.com")


@pytest.fixture
def auth_token(auth_user):
    """Generate a valid auth token for the test user."""
    return generate_jwt_token(auth_user)


class TestProtectedMobileEndpoint:
    """Test the protected mobile API endpoints."""

    def test_current_user_with_valid_token(self, client: Client, db, auth_user, auth_token):
        """Test accessing the currentuser endpoint with a valid token."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        response = client.get(reverse("mobile-api:current_user"), HTTP_AUTHORIZATION=auth_header)

        # Check response
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == auth_user.email
        assert data["name"] == str(auth_user.name)

    def test_current_user_without_token(self, client: Client, db):
        """Test accessing the currentuser endpoint without a token."""
        response = client.get(reverse("mobile-api:current_user"))

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_current_user_with_invalid_token(self, client: Client, db):
        """Test accessing the currentuser endpoint with an invalid token."""
        auth_header = "Bearer invalid.token.here"

        response = client.get(reverse("mobile-api:current_user"), HTTP_AUTHORIZATION=auth_header)

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_current_user_with_expired_token(self, client: Client, db, auth_user):
        """Test accessing the currentuser endpoint with an expired token."""
        # Create an expired token by setting expire_at to a time in the past
        expired_time = timezone.now() - timedelta(minutes=5)  # Expired 5 minutes ago
        expired_token = generate_jwt_token(auth_user, expire_at=expired_time)

        auth_header = f"Bearer {expired_token}"

        response = client.get(reverse("mobile-api:current_user"), HTTP_AUTHORIZATION=auth_header)

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_current_user_with_deactivated_user(self, client: Client, db, auth_user, auth_token):
        """Test accessing the currentuser endpoint with a deactivated user."""
        # Deactivate the user
        auth_user.is_active = False
        auth_user.save()

        auth_header = f"Bearer {auth_token}"

        response = client.get(reverse("mobile-api:current_user"), HTTP_AUTHORIZATION=auth_header)

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_current_user_with_nonexistent_user(self, client: Client, db):
        """Test accessing the currentuser endpoint with a token for a deleted user."""
        # Create a user and get a token
        temp_user = UserFactory()
        token = generate_jwt_token(temp_user)

        # Delete the user
        temp_user.delete()

        auth_header = f"Bearer {token}"

        response = client.get(reverse("mobile-api:current_user"), HTTP_AUTHORIZATION=auth_header)

        # Should return 401 Unauthorized
        assert response.status_code == 401
