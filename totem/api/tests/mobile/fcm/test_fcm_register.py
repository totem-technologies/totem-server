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


@pytest.fixture
def valid_fcm_token():
    """Generate a valid FCM token for testing."""
    return "fcm_token_" + "a" * 140  # Ensure token is long enough


class TestFCMRegistrationEndpoint:
    """Test the FCM token registration endpoint."""

    def test_register_token_success(self, client: Client, db, auth_user, auth_token, valid_fcm_token):
        """Test successful registration of a new FCM token."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload
        payload = {"token": valid_fcm_token, "device_id": "test_device_123", "device_type": "ios"}

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
        assert data["device_id"] == "test_device_123"
        assert data["device_type"] == "ios"
        assert data["active"] is True

        # Verify database state
        device = FCMDevice.objects.get(token=valid_fcm_token)
        assert device.user.id == auth_user.id
        assert device.device_id == "test_device_123"
        assert device.device_type == "ios"
        assert device.active is True

    def test_update_existing_token(self, client: Client, db, auth_user, auth_token, valid_fcm_token):
        """Test updating an existing token."""
        # Create an existing device
        FCMDevice.objects.create(
            user=auth_user, token=valid_fcm_token, device_id="old_device_id", device_type="android", active=True
        )

        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload with updated values
        payload = {"token": valid_fcm_token, "device_id": "updated_device_id", "device_type": "ios"}

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
        assert data["device_id"] == "updated_device_id"
        assert data["device_type"] == "ios"

        # Verify database state (should update not create)
        devices = FCMDevice.objects.filter(token=valid_fcm_token)
        assert devices.count() == 1
        device = devices.first()
        assert device
        assert device.user == auth_user
        assert device.device_id == "updated_device_id"
        assert device.device_type == "ios"

    def test_register_invalid_token_format(self, client: Client, db, auth_user, auth_token):
        """Test registration with invalid token format."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload with invalid token (None)
        payload = {"token": None, "device_id": "test_device_123", "device_type": "ios"}

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
        payload = {"token": "short_token", "device_id": "test_device_123", "device_type": "ios"}

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
        payload = {"token": token_with_invalid_chars, "device_id": "test_device_123", "device_type": "ios"}

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
        """Test registering a token that belongs to another user."""
        # Create another user with the same token
        other_user = UserFactory()
        FCMDeviceFactory(user=other_user, token=valid_fcm_token, device_id="other_device", device_type="android")

        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Prepare payload
        payload = {"token": valid_fcm_token, "device_id": "test_device_123", "device_type": "ios"}

        # Make the request
        response = client.post(
            reverse("mobile-api:register_fcm_token"),
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response - should fail without revealing the conflict
        assert response.status_code == 422
        assert "INVALID_TOKEN" in str(response.content)
        # Ensure we're not leaking information
        assert "another user" not in str(response.content)

    def test_register_without_authentication(self, client: Client, db, valid_fcm_token):
        """Test registration without authentication."""
        # Prepare payload
        payload = {"token": valid_fcm_token, "device_id": "test_device_123", "device_type": "ios"}

        # Make the request without auth header
        response = client.post(reverse("mobile-api:register_fcm_token"), payload, content_type="application/json")

        # Should return 401 Unauthorized
        assert response.status_code == 401
