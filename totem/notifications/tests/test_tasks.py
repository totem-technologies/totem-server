import pytest
from unittest.mock import patch
from django.utils import timezone
from datetime import timedelta

from totem.notifications.tasks import verify_fcm_tokens
from totem.notifications.tests.factories import FCMDeviceFactory
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestFCMTokenTasks:
    """Test the FCM token verification tasks."""

    @pytest.fixture
    def create_mixed_tokens(self):
        """Create a mix of tokens for testing (old/new, valid/invalid)."""
        user = UserFactory()

        # Create tokens with different last_used dates
        # 1. Old tokens (>30 days) that should be verified
        old_date = timezone.now() - timedelta(days=31)
        old_tokens = [FCMDeviceFactory(user=user, last_used=old_date, active=True) for _ in range(3)]

        # 2. Recent tokens that should not be verified
        recent_date = timezone.now() - timedelta(days=5)
        recent_tokens = [FCMDeviceFactory(user=user, last_used=recent_date, active=True) for _ in range(2)]

        # 3. Old but inactive tokens that should be ignored
        inactive_tokens = [FCMDeviceFactory(user=user, last_used=old_date, active=False) for _ in range(2)]

        return {
            "old_tokens": old_tokens,
            "recent_tokens": recent_tokens,
            "inactive_tokens": inactive_tokens,
            "user": user,
        }

    @patch("totem.notifications.tasks.validate_fcm_token")
    def test_verify_fcm_tokens(self, mock_validate, create_mixed_tokens):
        """Test that the verify_fcm_tokens task checks and updates old tokens correctly."""
        tokens = create_mixed_tokens

        # Configure the mock to return specific values for each token
        # First old token is valid, second is invalid, third is valid
        def side_effect(token):
            if token == tokens["old_tokens"][0].token or token == tokens["old_tokens"][2].token:
                return True
            return False

        mock_validate.side_effect = side_effect

        # Run the task
        verify_fcm_tokens()

        # Verify the mock was called for all old tokens, but not for recent or inactive ones
        assert mock_validate.call_count == len(tokens["old_tokens"])
        for token in tokens["old_tokens"]:
            mock_validate.assert_any_call(token.token)

        # Refresh tokens from the database
        for token in tokens["old_tokens"] + tokens["recent_tokens"] + tokens["inactive_tokens"]:
            token.refresh_from_db()

        # Check that only the invalid old token was deactivated
        assert tokens["old_tokens"][0].active is True
        assert tokens["old_tokens"][1].active is False  # This was marked invalid
        assert tokens["old_tokens"][2].active is True

        # Recent tokens should remain active
        for token in tokens["recent_tokens"]:
            assert token.active is True

        # Inactive tokens should remain inactive
        for token in tokens["inactive_tokens"]:
            assert token.active is False

    @patch("totem.notifications.tasks.validate_fcm_token")
    def test_verify_fcm_tokens_with_no_tokens(self, mock_validate):
        """Test the verify_fcm_tokens task when there are no tokens to verify."""
        # Run the task with no tokens in the database
        verify_fcm_tokens()

        # The validate function should not be called
        mock_validate.assert_not_called()

    @patch("totem.notifications.tasks.validate_fcm_token")
    @patch("totem.notifications.tasks.logger")
    def test_verify_fcm_tokens_logs_results(self, mock_logger, mock_validate, create_mixed_tokens):
        """Test that the task logs the verification results."""
        tokens = create_mixed_tokens

        # Configure mock to make some tokens valid and some invalid
        def side_effect(token):
            # Make the first token valid and the rest invalid
            return token == tokens["old_tokens"][0].token

        mock_validate.side_effect = side_effect

        # Run the task
        verify_fcm_tokens()

        # Verify that the results were logged
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]

        # Log should contain count of valid and invalid tokens
        assert "valid" in log_message
        assert "1 valid" in log_message  # Only one token is valid
        assert "invalidated" in log_message
        assert "2 invalidated" in log_message  # Two tokens are invalid
