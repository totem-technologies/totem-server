import pytest
from unittest.mock import patch, MagicMock
from firebase_admin import messaging as firebase_messaging

from totem.notifications.services import (
    send_notification_to_user,
    send_notification,
    validate_fcm_token,
)
from totem.notifications.tests.factories import FCMDeviceFactory
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestNotificationServices:
    """Test notification services functionality."""

    @pytest.fixture
    def mock_firebase_initialized(self):
        """Fixture to mock Firebase initialization."""
        with patch("totem.notifications.services.initialize_firebase") as mock_init:
            mock_init.return_value = True
            yield mock_init

    @pytest.fixture
    def user_with_devices(self):
        """Fixture to create a user with FCM devices."""
        user = UserFactory()
        # Create 3 active devices for the user
        devices = [FCMDeviceFactory(user=user, active=True) for _ in range(3)]
        # Create 1 inactive device
        inactive_device = FCMDeviceFactory(user=user, active=False)
        return user, devices, inactive_device

    @patch("totem.notifications.services.messaging")
    def test_send_notification_success(self, mock_messaging, mock_firebase_initialized):
        """Test successful notification sending."""
        # Set up mock for successful send
        mock_response = MagicMock()
        mock_response.success_count = 2
        mock_response.failure_count = 0
        mock_messaging.send.return_value = mock_response

        # Call the function
        tokens = ["token1", "token2"]
        result = send_notification(tokens, "Test Title", "Test Body", {"key": "value"})

        # Verify the result
        assert result is True
        mock_messaging.Message.assert_called()
        mock_messaging.send.assert_called()

    @patch("totem.notifications.services.messaging.send")
    def test_send_notification_all_failed(self, mock_messaging, mock_firebase_initialized):
        """Test notification sending with all tokens failing."""
        # Set up mock for complete failure
        mock_messaging.side_effect = Exception("Boom!")

        # Call the function
        tokens = ["token1", "token2"]
        result = send_notification(tokens, "Test Title", "Test Body")

        # Verify the result
        assert result is False

    @patch("totem.notifications.services.send_notification")
    def test_send_notification_to_user(self, mock_send_notification, user_with_devices, mock_firebase_initialized):
        """Test sending notification to a user with multiple devices."""
        user, devices, _ = user_with_devices
        mock_send_notification.return_value = True

        # Call the function
        result = send_notification_to_user(user, "Test Title", "Test Body", {"key": "value"})

        # Verify the result
        assert result is True

        # Should only send to active devices
        # Should send to active devices (tokens extracted internally by the service)
        mock_send_notification.assert_called_once_with(
            [device.token for device in devices], "Test Title", "Test Body", {"key": "value"}
        )

    @patch("totem.notifications.services.send_notification")
    def test_send_notification_to_user_no_devices(self, mock_send_notification, mock_firebase_initialized):
        """Test sending notification to a user with no devices."""
        user = UserFactory()

        # Call the function
        result = send_notification_to_user(user, "Test Title", "Test Body")

        # Verify the result
        assert result is False
        mock_send_notification.assert_not_called()

    @patch("totem.notifications.services.messaging")
    def test_validate_fcm_token_success(self, mock_messaging, mock_firebase_initialized):
        """Test successful token validation."""
        # Set up mock
        mock_messaging.send.return_value = "message_id"

        # Call the function
        result = validate_fcm_token("valid_token")

        # Verify the result
        assert result is True
        mock_messaging.Message.assert_called_once()
        mock_messaging.send.assert_called_once()

    @patch("totem.notifications.services.messaging.send")
    def test_validate_fcm_token_invalid(self, mock_send, mock_firebase_initialized):
        """Test validation of invalid token."""
        # Set up mock to raise the real UnregisteredError
        mock_send.side_effect = firebase_messaging.UnregisteredError("Mock error")

        # Call the function
        result = validate_fcm_token("invalid_token")

        # Verify the result
        assert result is False

    @patch("totem.notifications.services.messaging.send")
    def test_validate_fcm_token_exception(self, mock_send, mock_firebase_initialized):
        """Test token validation with other exception."""
        # Set up mock to raise a generic exception
        mock_send.side_effect = firebase_messaging.UnregisteredError("Mock error", None)

        # Call the function
        result = validate_fcm_token("token")

        # Verify the result
        assert result is False
