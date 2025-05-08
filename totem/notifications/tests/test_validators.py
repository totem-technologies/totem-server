import pytest
from ninja.errors import ValidationError

from totem.notifications.validators import validate_fcm_token


class TestFCMTokenValidator:
    """Test the FCM token validator function."""

    def test_valid_token(self):
        """Test validation with a valid token."""
        # Create a valid token (140+ characters with valid characters)
        valid_token = "a" * 140 + "b1234567890-_:"

        # Should not raise an exception
        result = validate_fcm_token(valid_token)
        assert result is True

    def test_none_token(self):
        """Test validation with None token."""
        with pytest.raises(ValidationError) as excinfo:
            validate_fcm_token(None)

        assert "INVALID_TOKEN" in str(excinfo.value)

    def test_empty_token(self):
        """Test validation with empty string token."""
        with pytest.raises(ValidationError) as excinfo:
            validate_fcm_token("")

        assert "INVALID_TOKEN" in str(excinfo.value)

    def test_non_string_token(self):
        """Test validation with non-string token."""
        with pytest.raises(ValidationError) as excinfo:
            validate_fcm_token(12345)

        assert "INVALID_TOKEN" in str(excinfo.value)

    def test_short_token(self):
        """Test validation with token shorter than 140 characters."""
        short_token = "a" * 139  # One character too short

        with pytest.raises(ValidationError) as excinfo:
            validate_fcm_token(short_token)

        assert "INVALID_TOKEN" in str(excinfo.value)

    def test_token_with_invalid_characters(self):
        """Test validation with token containing invalid characters."""
        # Valid length but contains invalid characters (@#$%)
        invalid_token = "a" * 136 + "@#$%"

        with pytest.raises(ValidationError) as excinfo:
            validate_fcm_token(invalid_token)

        assert "INVALID_TOKEN" in str(excinfo.value)

    def test_token_boundary_length(self):
        """Test validation with token exactly at the minimum length."""
        # Exactly 140 characters
        boundary_token = "a" * 140

        # Should not raise an exception
        result = validate_fcm_token(boundary_token)
        assert result is True

    def test_token_with_all_valid_characters(self):
        """Test validation with token containing all valid characters."""
        # Include all valid characters: a-z, A-Z, 0-9, :, _, -
        all_valid_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:_-"
        valid_token = all_valid_chars * 3  # Repeat to reach minimum length

        # Should not raise an exception
        result = validate_fcm_token(valid_token)
        assert result is True
