import pytest
from unittest.mock import patch

from totem.notifications.utils import notify_users
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestNotificationUtils:
    """Test notification utility functions."""

    @patch("totem.notifications.utils.send_notification_to_user")
    def test_notify_users(self, mock_send):
        """Test notify_users function with multiple users."""
        # Create test users
        users = [UserFactory() for _ in range(3)]

        # Configure mock to return True for first two users and False for the third
        mock_send.side_effect = [True, True, False]

        # Call the function
        result = notify_users(users, "Test Title", "Test Body", {"key": "value"})

        # Verify the result dictionary
        assert len(result) == 3
        assert result[users[0].pk] is True
        assert result[users[1].pk] is True
        assert result[users[2].pk] is False

        # Verify that send_notification_to_user was called for each user
        assert mock_send.call_count == 3

        # Check the arguments for each call
        for i, user in enumerate(users):
            mock_send.assert_any_call(user, "Test Title", "Test Body", {"key": "value"})

    @patch("totem.notifications.utils.send_notification_to_user")
    def test_notify_users_empty_list(self, mock_send):
        """Test notify_users with an empty user list."""
        # Call with empty list
        result = notify_users([], "Test Title", "Test Body")

        # Should return empty dict
        assert result == {}

        # Should not call send_notification_to_user
        mock_send.assert_not_called()

    @patch("totem.notifications.utils.send_notification_to_user")
    def test_notify_users_without_data(self, mock_send):
        """Test notify_users without data payload."""
        user = UserFactory()
        mock_send.return_value = True

        result = notify_users([user], "Test Title", "Test Body")

        assert result[user.pk] is True
        mock_send.assert_called_once_with(user, "Test Title", "Test Body", None)
