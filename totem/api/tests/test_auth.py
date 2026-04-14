from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken
from oauth2_provider.models import RefreshToken as OAuthRefreshToken

from totem.api.oauth import create_oauth_tokens
from totem.users.models import LoginPin, User
from totem.users.tests.factories import UserFactory


@pytest.fixture
def setup_user(oauth_app):
    return UserFactory(email="test@example.com")


class TestPinRequestEndpoint:
    """Test the PIN request endpoint."""

    def test_request_pin_new_user(self, client: Client, db, oauth_app):
        """Test requesting a PIN for a new user."""
        email = "neWuser+1234@example.COM"
        normalized_email = User.objects.normalize_email(email)
        response = client.post(
            reverse("mobile-api:auth_request_pin"),
            data={"email": email, "newsletter_consent": True},
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        assert response.json() == {"message": "PIN sent to your email"}

        # Check user was created
        user = User.objects.get(email=normalized_email)
        assert user.newsletter_consent is True
        assert not user.has_usable_password()

        # Check PIN was created and email sent
        pin = LoginPin.objects.get(user=user)
        assert pin.is_valid()
        assert len(mail.outbox) == 1  # PIN email
        assert mail.outbox[0].to == [normalized_email]
        assert pin.pin in mail.outbox[0].body

    def test_request_pin_existing_user_preserves_password(self, client: Client, db, oauth_app):
        """Existing user requesting a PIN should not change their password."""
        email = "eXisting@example.COM"
        normalized_email = User.objects.normalize_email(email)
        user = User.objects.create_user(email=email)
        original_password_hash = user.password

        response = client.post(
            reverse("mobile-api:auth_request_pin"),
            data={"email": user.email},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json() == {"message": "PIN sent to your email"}

        user.refresh_from_db()
        assert user.email == normalized_email
        assert user.password
        assert user.password == original_password_hash

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

    def test_request_pin_invalid_email(self, client: Client, db, oauth_app):
        """Test requesting a PIN with an invalid email address."""
        response = client.post(
            reverse("mobile-api:auth_request_pin"),
            data={"email": "隐藏邮件地址support@smartdeal.my", "newsletter_consent": False},
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "INVALID_EMAIL"}

        # Ensure no user was created
        assert User.objects.count() == 0

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
        """Test successful PIN validation returns OAuth tokens."""
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

        # Verify tokens exist in DOT tables
        assert AccessToken.objects.filter(token=data["access_token"], user=user).exists()
        assert OAuthRefreshToken.objects.filter(token=data["refresh_token"], user=user).exists()

    def test_validate_pin_nonexistent_user(self, client: Client, db, oauth_app):
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
        """Test successful token refresh with token rotation."""
        user = setup_user
        tokens = create_oauth_tokens(user)

        response = client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": tokens.refresh_token},
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["expires_in"] == 3600

        # Token should have been rotated (new refresh token)
        assert data["refresh_token"] != tokens.refresh_token

        # Old refresh token should be revoked
        old_refresh = OAuthRefreshToken.objects.get(token=tokens.refresh_token)
        assert old_refresh.revoked is not None

        # New tokens should be valid
        assert AccessToken.objects.filter(token=data["access_token"], user=user).exists()

    def test_refresh_token_invalid_token(self, client: Client, db, oauth_app):
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
        user = setup_user
        tokens = create_oauth_tokens(user)

        # Deactivate user
        user.is_active = False
        user.save()

        response = client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": tokens.refresh_token},
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "ACCOUNT_DEACTIVATED"}

        # Verify token was revoked
        old_refresh = OAuthRefreshToken.objects.get(token=tokens.refresh_token)
        assert old_refresh.revoked is not None

    def test_refresh_token_grace_period(self, client: Client, db, setup_user):
        """Test that a recently-revoked refresh token returns the replacement tokens (grace period)."""
        user = setup_user
        tokens = create_oauth_tokens(user)

        # Use the refresh token once (rotates it)
        first_response = client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": tokens.refresh_token},
            content_type="application/json",
        )
        assert first_response.status_code == 200
        first_data = first_response.json()

        # Use the old (now revoked) refresh token again within grace period
        second_response = client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": tokens.refresh_token},
            content_type="application/json",
        )

        # Should succeed and return the same replacement tokens
        assert second_response.status_code == 200
        second_data = second_response.json()
        assert second_data["access_token"] == first_data["access_token"]
        assert second_data["refresh_token"] == first_data["refresh_token"]

    def test_refresh_token_past_grace_period(self, client: Client, db, setup_user, settings):
        """Test that a revoked token past the grace period is rejected."""
        settings.OAUTH2_PROVIDER = {**settings.OAUTH2_PROVIDER, "REFRESH_TOKEN_GRACE_PERIOD_SECONDS": 0}
        user = setup_user
        tokens = create_oauth_tokens(user)

        # Use the refresh token once (rotates it)
        client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": tokens.refresh_token},
            content_type="application/json",
        )

        # Try again with no grace period
        response = client.post(
            reverse("mobile-api:auth_refresh"),
            data={"refresh_token": tokens.refresh_token},
            content_type="application/json",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "REAUTH_REQUIRED"}


class TestLogoutEndpoint:
    """Test the logout endpoint."""

    def test_logout_success(self, client: Client, db, setup_user):
        """Test successful logout."""
        user = setup_user
        tokens = create_oauth_tokens(user)

        response = client.post(
            reverse("mobile-api:auth_logout"),
            data={"refresh_token": tokens.refresh_token},
            content_type="application/json",
        )

        # Check response
        assert response.status_code == 200
        assert response.json() == {"message": "Successfully logged out"}

        # Verify refresh token was revoked
        old_refresh = OAuthRefreshToken.objects.get(token=tokens.refresh_token)
        assert old_refresh.revoked is not None

        # Verify access token was deleted (DOT's revoke() deletes access tokens)
        assert not AccessToken.objects.filter(token=tokens.access_token).exists()

    def test_logout_invalid_token(self, client: Client, db, oauth_app):
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

        # Verify OAuth tokens exist
        assert AccessToken.objects.filter(token=data["access_token"], user=user).exists()

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


class TestOAuthTokenOnProtectedEndpoint:
    """Test that OAuth tokens work on protected mobile endpoints."""

    def test_oauth_token_works(self, client: Client, db, setup_user):
        """Test that a DOT access token authenticates on protected endpoints."""
        user = setup_user
        tokens = create_oauth_tokens(user)

        response = client.get(
            reverse("mobile-api:user_current"),
            HTTP_AUTHORIZATION=f"Bearer {tokens.access_token}",
        )

        assert response.status_code == 200
        assert response.json()["email"] == user.email

    def test_expired_oauth_token_rejected(self, client: Client, db, setup_user, oauth_app):
        """Test that an expired DOT token is rejected."""
        from oauth2_provider.models import AccessToken as AT

        user = setup_user
        expired_token = AT.objects.create(
            user=user,
            application=oauth_app,
            token="expired-test-token",
            expires=timezone.now() - timedelta(minutes=5),
            scope="read write",
        )

        response = client.get(
            reverse("mobile-api:user_current"),
            HTTP_AUTHORIZATION=f"Bearer {expired_token.token}",
        )

        assert response.status_code == 401
