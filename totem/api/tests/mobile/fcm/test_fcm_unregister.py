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
    return UserFactory(email="fcm_unregister_test@example.com")


@pytest.fixture
def auth_token(auth_user):
    """Generate a valid auth token for the test user."""
    return generate_jwt_token(auth_user)


@pytest.fixture
def user_device(auth_user):
    """Create an FCM device for the test user."""
    return FCMDeviceFactory(
        user=auth_user,
        token="fcm_token_" + "a" * 140,
        device_id="test_device_123",
        device_type=FCMDevice.DEVICE_TYPE_IOS,
        active=True,
    )


class TestFCMUnregisterEndpoint:
    """Test the FCM token unregistration endpoint."""

    def test_unregister_token_success(self, client: Client, db, auth_user, auth_token, user_device):
        """Test successfully unregistering (marking inactive) an FCM token."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Make the request to unregister
        response = client.delete(
            reverse("mobile-api:unregister_fcm_token", kwargs={"token": user_device.token}),
            HTTP_AUTHORIZATION=auth_header,
        )

        # Check response
        assert response.status_code == 204

        # Verify the device was marked as inactive
        device = FCMDevice.objects.get(id=user_device.id)
        assert device.active is False

        # Verify it wasn't deleted
        assert FCMDevice.objects.filter(id=user_device.id).exists()

    def test_unregister_nonexistent_token(self, client: Client, db, auth_user, auth_token):
        """Test unregistering a token that doesn't exist."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Make the request with a non-existent token
        response = client.delete(
            reverse("mobile-api:unregister_fcm_token", kwargs={"token": "nonexistent_token_" + "a" * 140}),
            HTTP_AUTHORIZATION=auth_header,
        )

        # Should still return 204 (idempotent operation)
        assert response.status_code == 204

    def test_unregister_already_inactive_token(self, client: Client, db, auth_user, auth_token):
        """Test unregistering a token that's already inactive."""
        # Create an inactive device
        inactive_device = FCMDeviceFactory(user=auth_user, token="inactive_token_" + "a" * 140, active=False)

        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Make the request
        response = client.delete(
            reverse("mobile-api:unregister_fcm_token", kwargs={"token": inactive_device.token}),
            HTTP_AUTHORIZATION=auth_header,
        )

        # Should return 204
        assert response.status_code == 204

        # Device should still be inactive
        inactive_device.refresh_from_db()
        assert inactive_device.active is False

    def test_unregister_token_from_another_user(self, client: Client, db, auth_user, auth_token):
        """Test unregistering a token that belongs to another user."""
        # Create another user with a device
        other_user = UserFactory()
        other_device = FCMDeviceFactory(user=other_user, token="other_user_token_" + "a" * 140)

        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Make the request
        response = client.delete(
            reverse("mobile-api:unregister_fcm_token", kwargs={"token": other_device.token}),
            HTTP_AUTHORIZATION=auth_header,
        )

        # Should return 204 without revealing information about the token
        assert response.status_code == 204

        # The other user's device should not be affected
        other_device.refresh_from_db()
        assert other_device.active is True

    def test_unregister_without_authentication(self, client: Client, db, user_device):
        """Test unregistering without authentication."""
        # Make the request without auth header
        response = client.delete(reverse("mobile-api:unregister_fcm_token", kwargs={"token": user_device.token}))

        # Should return 401 Unauthorized
        assert response.status_code == 401

        # Device should still be active
        user_device.refresh_from_db()
        assert user_device.active is True
