from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse

from totem.users.models import LoginPin, User
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestHoneypotProtection:
    """Test honeypot field protection against bots."""

    def test_legitimate_signup_honeypot_empty(self, client):
        """Test that legitimate signup with empty honeypot works normally."""
        email = "legitimate@example.com"

        # Submit signup with empty honeypot
        response = client.post(
            reverse("users:signup"),
            {
                "email": email,
                "website": "",  # Honeypot field empty
                "newsletter_consent": True,
            },
        )

        assert response.status_code == 302
        assert response.url.startswith(reverse("users:verify-pin"))

        # Check user was created with consent
        user = User.objects.get(email=email)
        assert user.newsletter_consent is True
        assert len(mail.outbox) == 1

    @patch("totem.users.views.logger")
    def test_bot_login_honeypot_filled(self, mock_logger, client):
        """Test that bot login with filled honeypot is blocked."""
        email = "bot@spammer.com"

        # Submit login with filled honeypot (bot behavior)
        response = client.post(
            reverse("users:login"),
            {
                "email": email,
                "website": "http://spam-site.com",  # Bot filled the honeypot!
            },
        )

        # Should still redirect (to not reveal detection to bot)
        assert response.status_code == 302
        assert response.url.startswith(reverse("users:verify-pin"))

        # But user should NOT be created
        assert not User.objects.filter(email=email).exists()

        # No email should be sent
        assert len(mail.outbox) == 0

    @patch("totem.users.views.logger")
    def test_bot_signup_honeypot_filled(self, mock_logger, client):
        """Test that bot signup with filled honeypot is blocked."""
        email = "bot@spammer.com"

        # Submit signup with filled honeypot
        response = client.post(
            reverse("users:signup"),
            {
                "email": email,
                "website": "Buy cheap meds!",  # Bot filled the honeypot!
                "newsletter_consent": True,
            },
        )

        # Should still redirect (silent failure)
        assert response.status_code == 302
        assert response.url.startswith(reverse("users:verify-pin"))

        # User should NOT be created
        assert not User.objects.filter(email=email).exists()

        # No email sent
        assert len(mail.outbox) == 0

    def test_honeypot_field_not_visible_in_form_rendering(self, client):
        """Test that honeypot field is properly hidden in HTML."""
        response = client.get(reverse("users:login"))
        content = response.content.decode()

        # Check that the field exists but is hidden
        assert 'name="website"' in content
        assert 'aria-hidden="true"' in content
        assert 'tabindex="-1"' in content
        assert "position: absolute" in content

    def test_existing_user_with_honeypot(self, client):
        """Test that existing users are also protected by honeypot."""
        user = UserFactory()

        # Try to login existing user with filled honeypot
        response = client.post(reverse("users:login"), {"email": user.email, "website": "spam content"})

        # Should redirect but not actually process
        assert response.status_code == 302

        # No PIN should be created
        assert not LoginPin.objects.filter(user=user).exists()

        # No email sent
        assert len(mail.outbox) == 0

    def test_honeypot_with_various_content(self, client):
        """Test honeypot triggers with various bot-like content."""
        test_cases = [
            "http://example.com",
            "Buy now!",
            "<script>alert('xss')</script>",
            "1234567890",
            "x",  # Even single character should trigger
        ]

        for content in test_cases:
            mail.outbox.clear()
            email = f"bot{len(test_cases)}@example.com"

            client.post(reverse("users:login"), {"email": email, "website": content})

            # All should be blocked
            assert not User.objects.filter(email=email).exists()
            assert len(mail.outbox) == 0

    def test_honeypot_field_completely_missing(self, client):
        """Test form submission without honeypot field at all (old form or bypass attempt)."""
        email = "test@example.com"

        # Submit without honeypot field - should work (backward compatibility)
        response = client.post(
            reverse("users:login"),
            {
                "email": email,
                # No 'website' field at all
            },
        )

        assert response.status_code == 302
        assert User.objects.filter(email=email).exists()
