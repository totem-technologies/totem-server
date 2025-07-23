from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.users.models import LoginPin, RefreshToken, User
from totem.users.tests.factories import UserFactory


@pytest.fixture
def setup_user():
    return UserFactory(email="test@example.com")


class TestPinRequestEndpoint:
    """Test the PIN request endpoint."""

    def test_request_pin_new_user(self, client: Client, db):
        """Test requesting a PIN for a new user."""
        email = "newuser+1234@example.com"
        response = client.post(
            reverse("mobile-api:auth_request_pin"),
            data={"email": email, "newsletter_consent": True},
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        assert response.json() == {"message": "PIN sent to your email"}

        # Check user was created
        user = User.objects.get(email=email)
        assert user.newsletter_consent is True

        # Check PIN was created and email sent
        pin = LoginPin.objects.get(user=user)
        assert pin.is_valid()
        assert len(mail.outbox) == 1  # PIN email
        assert mail.outbox[0].to == [email]
        assert pin.pin in mail.outbox[0].body

    def test_request_pin_existing_user(self, client: Client, db, setup_user):
        """Test requesting PIN for existing user."""
        user = setup_user
        response = client.post(
            reverse("mobile-api:auth_request_pin"),
            data={"email": user.email, "newsletter_consent": True},
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        assert response.json() == {"message": "PIN sent to your email"}

        # Check newsletter_consent was updated
        user.refresh_from_db()
        assert user.newsletter_consent is True

        # Check PIN was created and email sent
        pin = LoginPin.objects.get(user=user)
        assert pin.is_valid()
        assert len(mail.outbox) == 1  # Only PIN email, no welcome email for existing users
        assert mail.outbox[0].to == [user.email]
        assert pin.pin in mail.outbox[0].body

    def test_request_pin_case_insensitive(self, client: Client, db, setup_user):
        """Test email case insensitivity."""
        user = setup_user
        uppercase_email = user.email.upper()

        response = client.post(
            reverse("mobile-api:auth_request_pin"),
            data={"email": uppercase_email},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]  # Should use normalized email


class TestPinValidationEndpoint:
    """Test the PIN validation endpoint."""

    def test_validate_pin_success(self, client: Client, db, setup_user):
        """Test successful PIN validation."""
        user = setup_user
        pin = LoginPin.objects.generate_pin(user)

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": pin.pin,
            },
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["expires_in"] == 3600

        # Decode and verify access token
        payload = jwt.decode(data["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
        assert str(user.api_key) == payload["api_key"]
        assert "exp" in payload

        # Verify refresh token was created
        assert RefreshToken.objects.filter(user=user).exists()

    def test_validate_pin_nonexistent_user(self, client: Client, db):
        """Test PIN validation with nonexistent user."""
        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": "nonexistent@example.com",
                "pin": "123456",
            },
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "INCORRECT_PIN"}

    def test_validate_pin_incorrect_pin(self, client: Client, db, setup_user):
        """Test PIN validation with incorrect PIN."""
        user = setup_user
        pin = LoginPin.objects.generate_pin(user)

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": "000000",  # Wrong PIN
            },
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "PIN_EXPIRED"}

        # Check failed attempts counter
        pin.refresh_from_db()
        assert pin.failed_attempts == 1

    def test_validate_pin_expired(self, client: Client, db, setup_user):
        """Test PIN validation with expired PIN."""
        user = setup_user
        pin = LoginPin.objects.generate_pin(user)

        # Make PIN expired
        pin.expires_at = timezone.now() - timedelta(minutes=1)
        pin.save()

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": pin.pin,
            },
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "PIN_EXPIRED"}

    def test_validate_pin_too_many_attempts(self, client: Client, db, setup_user):
        """Test PIN validation with too many attempts."""
        user = setup_user
        pin = LoginPin.objects.generate_pin(user)

        # Set high attempt count
        pin.failed_attempts = LoginPin.MAX_ATTEMPTS
        pin.save()

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": pin.pin,
            },
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "PIN_EXPIRED"}

    def test_validate_pin_deactivated_account(self, client: Client, db, setup_user):
        """Test PIN validation with deactivated account."""
        user = setup_user
        pin = LoginPin.objects.generate_pin(user)

        # Deactivate user
        user.is_active = False
        user.save()

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": pin.pin,
            },
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "ACCOUNT_DEACTIVATED"}


class TestRefreshTokenEndpoint:
    """Test the token refresh endpoint."""

    def test_refresh_token_success(self, client: Client, db, setup_user):
        """Test successful token refresh."""
        # Setup: create a refresh token
        user = setup_user
        refresh_token, token_obj = RefreshToken.objects.generate_token(user)

        response = client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": refresh_token},
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["refresh_token"] == refresh_token
        assert data["expires_in"] == 3600

        # Verify token was updated (last_used_at)
        token_obj.refresh_from_db()
        assert (timezone.now() - token_obj.last_used_at).total_seconds() < 10

    def test_refresh_token_invalid_token(self, client: Client, db):
        """Test refresh with invalid token."""
        response = client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": "invalid-token"},
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "REAUTH_REQUIRED"}

    def test_refresh_token_deactivated_account(self, client: Client, db, setup_user):
        """Test refresh with deactivated account."""
        # Setup: create a refresh token
        user = setup_user
        refresh_token, token_obj = RefreshToken.objects.generate_token(user)

        # Deactivate user
        user.is_active = False
        user.save()

        response = client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": refresh_token},
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "ACCOUNT_DEACTIVATED"}

        # Verify token was invalidated
        token_obj.refresh_from_db()
        assert token_obj.is_active is False


class TestLogoutEndpoint:
    """Test the logout endpoint."""

    def test_logout_success(self, client: Client, db, setup_user):
        """Test successful logout."""
        # Setup: create a refresh token
        user = setup_user
        refresh_token, token_obj = RefreshToken.objects.generate_token(user)

        response = client.post(
            reverse("mobile-api:auth_logout"),
            data={"refresh_token": refresh_token},
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        assert response.json() == {"message": "Successfully logged out"}

        # Verify token was invalidated
        token_obj.refresh_from_db()
        assert token_obj.is_active is False

    def test_logout_invalid_token(self, client: Client, db):
        """Test logout with invalid token."""
        response = client.post(
            reverse("mobile-api:auth_logout"),
            data={"refresh_token": "invalid-token"},
            content_type="application/json",
        )

        # Should still return success even for invalid token
        assert response.status_code == 200
        assert response.json() == {"message": "Successfully logged out"}


class TestFixedPinEndpoint:
    """Test the fixed PIN functionality."""

    def test_fixed_pin_success(self, client: Client, db, setup_user):
        """Test successful fixed PIN validation."""
        user = setup_user
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True
        user.save()

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": "123456",
            },
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["expires_in"] == 3600

        # Decode and verify access token
        payload = jwt.decode(data["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
        assert str(user.api_key) == payload["api_key"]

    def test_fixed_pin_disabled(self, client: Client, db, setup_user):
        """Test fixed PIN validation when disabled."""
        user = setup_user
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = False  # Disabled
        user.save()

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": "123456",
            },
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "PIN_EXPIRED"}

    def test_fixed_pin_incorrect(self, client: Client, db, setup_user):
        """Test fixed PIN validation with incorrect PIN."""
        user = setup_user
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True
        user.save()

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": "000000",  # Wrong PIN
            },
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "PIN_EXPIRED"}

    def test_fixed_pin_fallback_after_regular_pin(self, client: Client, db, setup_user):
        """Test that fixed PIN works as fallback when regular PIN exists but is wrong."""
        user = setup_user
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True
        user.save()

        # Create a regular PIN first
        LoginPin.objects.generate_pin(user)

        # Try with fixed PIN (should work as fallback)
        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": "123456",
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    def test_fixed_pin_staff_user_validation(self, client: Client, db, setup_user):
        """Test that staff users cannot enable fixed PIN."""
        user = setup_user
        user.is_staff = True
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True

        # This should raise a ValidationError during model validation
        with pytest.raises(Exception):  # ValidationError will be raised
            user.full_clean()

    def test_fixed_pin_empty_pin(self, client: Client, db, setup_user):
        """Test fixed PIN validation with empty PIN."""
        user = setup_user
        user.fixed_pin = ""  # Empty PIN
        user.fixed_pin_enabled = True
        user.save()

        response = client.post(
            reverse("mobile-api:auth_validate_pin"),
            data={
                "email": user.email,
                "pin": "123456",
            },
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "PIN_EXPIRED"}
