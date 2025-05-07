import pytest

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
