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
    return UserFactory(email="fcm_list_test@example.com")


@pytest.fixture
def auth_token(auth_user):
    """Generate a valid auth token for the test user."""
    return generate_jwt_token(auth_user)


@pytest.fixture
def user_devices(auth_user):
    """Create several FCM devices for the test user."""
    devices = [
        FCMDeviceFactory(user=auth_user, device_type=FCMDevice.DEVICE_TYPE_IOS, device_id=f"ios_device_{i}")
        for i in range(2)
    ]

    devices.extend(
        [
            FCMDeviceFactory(user=auth_user, device_type=FCMDevice.DEVICE_TYPE_ANDROID, device_id=f"android_device_{i}")
            for i in range(2)
        ]
    )

    # Create an inactive device
    inactive_device = FCMDeviceFactory(user=auth_user, active=False, device_id="inactive_device")

    return devices + [inactive_device]


class TestFCMListDevicesEndpoint:
    """Test the FCM devices listing endpoint."""

    def test_list_devices_success(self, client: Client, db, auth_user, auth_token, user_devices):
        """Test successfully listing all FCM devices for the current user."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Make the request
        response = client.get(reverse("mobile-api:list_fcm_devices"), HTTP_AUTHORIZATION=auth_header)

        # Check response
        assert response.status_code == 200
        data = response.json()

        # Should return all devices including inactive ones
        assert len(data) == len(user_devices)

        # Verify response format for each device
        for device_data in data:
            assert "id" in device_data
            assert "token" in device_data
            assert "device_id" in device_data
            assert "device_type" in device_data
            assert "active" in device_data
            assert "created_at" in device_data

        # Check that all our device IDs are present
        device_ids_in_response = [d["device_id"] for d in data]
        for device in user_devices:
            assert device.device_id in device_ids_in_response

    def test_list_devices_empty(self, client: Client, db, auth_user, auth_token):
        """Test listing devices when user has no devices."""
        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Make the request
        response = client.get(reverse("mobile-api:list_fcm_devices"), HTTP_AUTHORIZATION=auth_header)

        # Check response
        assert response.status_code == 200
        data = response.json()

        # Should return an empty list
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_devices_only_returns_users_own_devices(self, client: Client, db, auth_user, auth_token):
        """Test that the endpoint only returns the user's own devices."""
        # Create some devices for the auth user
        own_devices = [FCMDeviceFactory(user=auth_user) for _ in range(2)]

        # Create devices for another user
        other_user = UserFactory()
        other_devices = [FCMDeviceFactory(user=other_user) for _ in range(3)]

        # Construct the authorization header
        auth_header = f"Bearer {auth_token}"

        # Make the request
        response = client.get(reverse("mobile-api:list_fcm_devices"), HTTP_AUTHORIZATION=auth_header)

        # Check response
        assert response.status_code == 200
        data = response.json()

        # Should only return auth_user's devices
        assert len(data) == len(own_devices)

        # Extract IDs from response
        device_ids = [d["id"] for d in data]

        # Verify only the user's devices are returned
        for device in own_devices:
            assert device.id in device_ids

        for device in other_devices:
            assert device.id not in device_ids

    def test_list_devices_without_authentication(self, client: Client, db):
        """Test listing devices without authentication."""
        # Make the request without auth header
        response = client.get(reverse("mobile-api:list_fcm_devices"))

        # Should return 401 Unauthorized
        assert response.status_code == 401
