import random

import pytest
from django.test import Client
from django.urls import reverse

from totem.api.auth import generate_jwt_token
from totem.notifications.models import FCMDevice
from totem.notifications.tests.factories import FCMDeviceFactory
from totem.users.tests.factories import UserFactory


@pytest.fixture
def auth_user():
    """Create a user for testing authentication."""
    return UserFactory(email="fcm_test@example.com")


@pytest.fixture
def auth_token(auth_user):
    """Generate a valid auth token for the test user."""
    return generate_jwt_token(auth_user)


TOKEN_SEED = 1


@pytest.fixture
def valid_fcm_token() -> str:
    """Generate a random valid FCM token for testing, using TOKEN_SEED"""
    global TOKEN_SEED
    TOKEN_SEED += 1
    print(TOKEN_SEED)
    # random 140 character string with TOKEN_SEED as the seed
    token = random.Random(TOKEN_SEED).randint(0, 10**140)
    return "fcm_token_" + str(token)


class TestFCMRegistrationEndpoint:
    """Test the FCM token registration endpoint."""

    def test_register_token_success(self, client: Client, db, auth_user, auth_token, valid_fcm_token):
        """Test successful registration of a new FCM token."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload
        payload = {"token": valid_fcm_token}

        # Make the request
        response = client.post(
            reverse("mobile-api:register_fcm_token"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response
        assert response.status_code == 201
        data = response.json()
        assert data["token"] == valid_fcm_token
        assert data["active"] is True

        # Verify database state
        device = FCMDevice.objects.get(token=valid_fcm_token)
        assert device.user == auth_user
        assert device.active is True

    def test_update_existing_token(self, client: Client, db, auth_user, auth_token, valid_fcm_token):
        """Test updating an existing token."""
        # Create an existing device
        existing_device = FCMDevice.objects.create(user=auth_user, token=valid_fcm_token, active=False)
        original_updated_at = existing_device.updated_at

        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload with updated values
        payload = {"token": valid_fcm_token}

        # Make the request
        response = client.post(
            reverse("mobile-api:register_fcm_token"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response
        assert response.status_code == 201
        data = response.json()
        assert data["token"] == valid_fcm_token
        assert data["active"] is True

        # Verify database state (should update not create)
        devices = FCMDevice.objects.filter(token=valid_fcm_token)
        assert devices.count() == 1
        device = devices.first()
        assert device
        assert device.user == auth_user
        assert device.active is True
        assert device.updated_at > original_updated_at  # Verify updated_at was updated

    def test_register_invalid_token_format(self, client: Client, db, auth_user, auth_token):
        """Test registration with invalid token format."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload with invalid token (None)
        payload = {"token": None}

        # Make the request
        response = client.post(
            reverse("mobile-api:register_fcm_token"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response (expected validation error)
        assert response.status_code == 422  # Validation error status code

    def test_register_token_too_short(self, client: Client, db, auth_user, auth_token):
        """Test registration with token that's too short."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload with short token
        payload = {"token": "short_token"}

        # Make the request
        response = client.post(
            reverse("mobile-api:register_fcm_token"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response
        assert response.status_code == 422
        assert "INVALID_TOKEN" in str(response.content)

    def test_register_token_with_invalid_characters(self, client: Client, db, auth_user, auth_token):
        """Test registration with token containing invalid characters."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload with invalid characters
        token_with_invalid_chars = "a" * 136 + "@#$%"
        payload = {"token": token_with_invalid_chars}

        # Make the request
        response = client.post(
            reverse("mobile-api:register_fcm_token"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response
        assert response.status_code == 422
        assert "INVALID_TOKEN" in str(response.content)

    def test_register_token_from_another_user(self, client: Client, db, auth_user, auth_token, valid_fcm_token):
        """Test registering a token that belongs to another user - should reassign to current user."""
        # Create another user with the same token
        other_user = UserFactory()
        existing_device = FCMDeviceFactory(user=other_user, token=valid_fcm_token, active=False)

        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload
        payload = {"token": valid_fcm_token}

        # Make the request
        response = client.post(
            reverse("mobile-api:register_fcm_token"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response - should succeed
        assert response.status_code == 201
        data = response.json()
        assert data["token"] == valid_fcm_token
        assert data["active"] is True

        # Verify database state - token reassigned to auth_user
        devices = FCMDevice.objects.filter(token=valid_fcm_token)
        assert devices.count() == 1
        device = devices.first()
        if device is None:
            raise ValueError("Device not found")
        assert device.user == auth_user  # Reassigned to current user
        assert device.active is True
        assert device.updated_at > existing_device.updated_at  # Updated timestamp

    def test_register_duplicate_tokens(self, client: Client, db, auth_user, auth_token, valid_fcm_token):
        """Test registering when multiple duplicate tokens exist - should delete all and create new."""
        # Create multiple devices with the same token (simulating a bug scenario)
        other_user1 = UserFactory()
        other_user2 = UserFactory()
        FCMDeviceFactory(user=other_user1, token=valid_fcm_token)
        FCMDeviceFactory(user=other_user2, token=valid_fcm_token)
        FCMDeviceFactory(user=auth_user, token=valid_fcm_token)

        # Verify duplicates exist
        assert FCMDevice.objects.filter(token=valid_fcm_token).count() == 3

        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload
        payload = {"token": valid_fcm_token}

        # Make the request
        response = client.post(
            reverse("mobile-api:register_fcm_token"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response
        assert response.status_code == 201
        data = response.json()
        assert data["token"] == valid_fcm_token
        assert data["active"] is True

        # Verify database state - all duplicates deleted, new one created
        devices = FCMDevice.objects.filter(token=valid_fcm_token)
        assert devices.count() == 1
        device = devices.first()
        if device is None:
            raise ValueError("Device not found")
        assert device.user == auth_user
        assert device.active is True

    def test_register_without_authentication(self, client: Client, db, valid_fcm_token):
        """Test registration without authentication."""
        # Prepare payload
        payload = {"token": valid_fcm_token}

        # Make the request without auth header
        response = client.post(reverse("mobile-api:register_fcm_token"), payload, content_type="application/json")

        # Should return 401 Unauthorized
        assert response.status_code == 401
