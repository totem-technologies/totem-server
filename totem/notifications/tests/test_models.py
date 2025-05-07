import pytest
from django.db import IntegrityError

from totem.notifications.models import FCMDevice
from totem.notifications.tests.factories import FCMDeviceFactory
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestFCMDeviceModel:
    """Test the FCMDevice model."""

    def test_create_fcm_device(self):
        """Test creating an FCMDevice."""
        user = UserFactory()
        device = FCMDevice.objects.create(
            user=user,
            token="fcm_token_abcdefghijklmnopqrstuvwxyz1234567890fcm_token_abcdefghijklmnopqrstuvwxyz1234567890"
            "fcm_token_abcdefghijklmnopqrstuvwxyz1234567890fcm_token_abcdefghijklmnopqrstuvwxyz1234567890",
        )
        assert device.user == user
        assert device.token.startswith("fcm_token_")
        assert device.active is True
        assert device.created_at is not None
        assert device.updated_at is not None

    def test_device_str_representation(self):
        """Test the string representation of the FCMDevice model."""
        device = FCMDeviceFactory()
        expected_str = f"{device.user.username} - ({device.token[:10]}...)"
        assert str(device) == expected_str

    def test_unique_together_constraint(self):
        """Test that a user cannot have multiple devices with the same token."""
        user = UserFactory()
        token = (
            "fcm_token_abcdefghijklmnopqrstuvwxyz1234567890fcm_token_abcdefghijklmnopqrstuvwxyz1234567890"
            "fcm_token_abcdefghijklmnopqrstuvwxyz1234567890fcm_token_abcdefghijklmnopqrstuvwxyz1234567890"
        )

        # Create first device
        FCMDevice.objects.create(
            user=user,
            token=token,
        )

        # Try to create another device with the same token and user
        with pytest.raises(IntegrityError):
            FCMDevice.objects.create(
                user=user,
                token=token,
            )

    def test_same_token_different_users(self):
        """Test that different users can have devices with the same token (though this shouldn't happen in practice)."""
        user1 = UserFactory()
        user2 = UserFactory()
        token = (
            "fcm_token_abcdefghijklmnopqrstuvwxyz1234567890fcm_token_abcdefghijklmnopqrstuvwxyz1234567890"
            "fcm_token_abcdefghijklmnopqrstuvwxyz1234567890fcm_token_abcdefghijklmnopqrstuvwxyz1234567890"
        )

        # Create device for first user
        device1 = FCMDevice.objects.create(
            user=user1,
            token=token,
        )

        # Create device for second user with same token
        device2 = FCMDevice.objects.create(
            user=user2,
            token=token,
        )

        assert device1.token == device2.token
        assert device1.user != device2.user
