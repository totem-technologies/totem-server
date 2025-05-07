from firebase_admin import messaging
import pytest
from unittest.mock import patch, MagicMock

from totem.notifications.services import (
    initialize_firebase,
    send_notification_to_user,
    send_notification,
    validate_fcm_token,
)
from totem.notifications.tests.factories import FCMDeviceFactory
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestFirebaseInitialization:
    """Test Firebase initialization functionality."""

    @patch("totem.notifications.services.firebase_admin")
    @patch("totem.notifications.services.credentials")
    def test_initialize_firebase_success(self, mock_credentials, mock_firebase_admin):
        """Test successful Firebase initialization."""
        # Set up mocks
        mock_credentials.Certificate.return_value = "mock_credentials"
        mock_firebase_admin._apps = {}

        # Call the function
        result = initialize_firebase()

        # Verify the result
        assert result is True
        mock_credentials.Certificate.assert_called_once()
        mock_firebase_admin.initialize_app.assert_called_once()

    @patch("totem.notifications.services.firebase_admin")
    @patch("totem.notifications.services.credentials")
    def test_initialize_firebase_already_initialized(self, mock_credentials, mock_firebase_admin):
        """Test Firebase initialization when already initialized."""
        # Set up mocks to simulate Firebase already being initialized
        mock_firebase_admin._apps = {"totem": "mock_app"}

        # Call the function
        result = initialize_firebase()

        # Should return True without initializing again
        assert result is True
        mock_credentials.Certificate.assert_not_called()
        mock_firebase_admin.initialize_app.assert_not_called()

    @patch("totem.notifications.services.firebase_admin")
    @patch("totem.notifications.services.credentials")
    @patch("totem.notifications.services.logger")
    def test_initialize_firebase_error(self, mock_logger, mock_credentials, mock_firebase_admin):
        """Test Firebase initialization with error."""
        # Set up mocks to raise an exception
        mock_credentials.Certificate.side_effect = Exception("Mock error")
        mock_firebase_admin._apps = {}

        # Call the function
        result = initialize_firebase()

        # Should return False and log the error
        assert result is False
        mock_logger.error.assert_called_once()
        assert "Mock error" in mock_logger.error.call_args[0][0]


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
        mock_messaging.send_multicast.return_value = mock_response

        # Call the function
        tokens = ["token1", "token2"]
        result = send_notification(tokens, "Test Title", "Test Body", {"key": "value"})

        # Verify the result
        assert result is True
        mock_messaging.MulticastMessage.assert_called_once()
        mock_messaging.send_multicast.assert_called_once()

    @patch("totem.notifications.services.messaging")
    def test_send_notification_partial_failure(self, mock_messaging, mock_firebase_initialized):
        """Test notification sending with some failed tokens."""
        # Set up mock for partial success
        mock_response = MagicMock()
        mock_response.success_count = 1
        mock_response.failure_count = 1
        mock_response.responses = [MagicMock(success=True), MagicMock(success=False)]
        mock_messaging.send_multicast.return_value = mock_response

        # Create a device to test deactivation
        device = FCMDeviceFactory(token="token2", active=True)

        # Call the function
        tokens = ["token1", "token2"]
        result = send_notification(tokens, "Test Title", "Test Body")

        # Verify the result
        assert result is True  # Still True because at least one succeeded

        # Verify the device was deactivated
        device.refresh_from_db()
        assert device.active is False

    @patch("totem.notifications.services.messaging")
    def test_send_notification_all_failed(self, mock_messaging, mock_firebase_initialized):
        """Test notification sending with all tokens failing."""
        # Set up mock for complete failure
        mock_response = MagicMock()
        mock_response.success_count = 0
        mock_response.failure_count = 2
        mock_response.responses = [MagicMock(success=False), MagicMock(success=False)]
        mock_messaging.send_multicast.return_value = mock_response

        # Call the function
        tokens = ["token1", "token2"]
        result = send_notification(tokens, "Test Title", "Test Body")

        # Verify the result
        assert result is False

    @patch("totem.notifications.services.messaging.send_multicast")
    def test_send_notification_exception(self, send_multicast_mock, mock_firebase_initialized):
        """Test notification sending with exception."""
        # Set up mock to raise an exception
        send_multicast_mock.side_effect = messaging.UnregisteredError("Mock error")

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

    @patch("totem.notifications.services.messaging")
    def test_validate_fcm_token_invalid(self, mock_messaging, mock_firebase_initialized):
        """Test validation of invalid token."""
        # Set up mock to raise an UnregisteredError
        mock_messaging.UnregisteredError = Exception
        mock_messaging.send.side_effect = mock_messaging.UnregisteredError()

        # Call the function
        result = validate_fcm_token("invalid_token")

        # Verify the result
        assert result is False

    @patch("totem.notifications.services.messaging")
    def test_validate_fcm_token_exception(self, mock_messaging, mock_firebase_initialized):
        """Test token validation with other exception."""
        # Set up mock to raise a generic exception
        mock_messaging.send.side_effect = Exception("Mock error")

        # Call the function
        result = validate_fcm_token("token")

        # Verify the result
        assert result is False
