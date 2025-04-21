import pytest
from django.core import mail
from django.urls import reverse

from totem.users.models import User, LoginPin
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestLogInView:
    def test_login_new_user(self, client):
        email = "testuser@totem.org"
        with pytest.raises(User.DoesNotExist):
            User.objects.get(email=email)

        # Submit login request
        response = client.post(reverse("users:login"), {"email": email})
        assert response.status_code == 302  # Should redirect to PIN verification
        assert response.url.startswith(reverse("users:verify-pin"))

        # Check that an email with PIN was sent
        assert len(mail.outbox) == 1  # Just PIN email in test mode
        assert "PIN" in mail.outbox[0].body
        # Get the PIN from the most recent LoginPin object
        pin = LoginPin.objects.get(user__email=email).pin
        assert pin in mail.outbox[0].body

        # Check that a new user was created
        count = User.objects.count()
        assert count == 1
        user = User.objects.get(email=email)
        assert user.email == email
        assert user.newsletter_consent is False
        assert not user.verified  # User should not be verified until PIN verification

    def test_signup_new_with_consent(self, client):
        assert len(mail.outbox) == 0
        email = "testuserconsent@totem.org"
        with pytest.raises(User.DoesNotExist):
            User.objects.get(email=email)

        # Check signup form has newsletter consent
        response = client.get(reverse("users:signup"))
        assert "newsletter_consent" in response.content.decode()

        # Submit signup with consent
        response = client.post(reverse("users:signup"), {"email": email, "newsletter_consent": True})
        assert response.status_code == 302
        assert response.url.startswith(reverse("users:verify-pin"))

        # Check emails sent (just PIN in test mode)
        assert len(mail.outbox) == 1
        assert "PIN" in mail.outbox[0].body

        # Verify user created with consent
        user = User.objects.get(email=email)
        assert user.newsletter_consent is True
        assert not user.verified

    def test_login_existing_user(self, client):
        # Create an existing user
        user = UserFactory()
        count = User.objects.count()

        # Submit the login form
        response = client.post(reverse("users:login"), {"email": user.email})
        assert response.status_code == 302
        assert response.url.startswith(reverse("users:verify-pin"))

        # Check that PIN email was sent
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert "PIN" in mail.outbox[0].body

        # Check that no new user was created
        assert User.objects.count() == count

    def test_login_failure(self, client):
        # Submit the login form with an invalid email
        response = client.post(reverse("users:login"), {"email": "invalid"})
        # Check that the response shows error
        assert response.status_code == 200
        assert b"error" in response.content
        # Check that no email was sent
        assert len(mail.outbox) == 0

    def test_login_parameters(self, client):
        # Create an existing user
        user = UserFactory()
        count = User.objects.count()

        # Submit login with after_login_url
        response = client.post(
            reverse("users:login"),
            {
                "email": user.email,
                "after_login_url": "/foo",
            },
        )
        assert response.status_code == 302
        assert response.url.startswith(reverse("users:verify-pin"))

        # Get PIN and verify
        pin = LoginPin.objects.get(user=user).pin

        # Verify PIN and check redirect
        response = client.post(reverse("users:verify-pin"), {"email": user.email, "pin": pin})
        assert response.status_code == 302
        assert response.url == "/foo"

        # Check that no new user was created
        assert User.objects.count() == count

    def test_login_parameters_attacker(self, client):
        # Create an existing user
        user = UserFactory()
        count = User.objects.count()

        # Try to redirect to attacker site
        response = client.post(
            reverse("users:login"),
            {
                "email": user.email,
                "after_login_url": "https://attacker.com",
            },
        )
        assert response.status_code == 302
        assert response.url.startswith(reverse("users:verify-pin"))

        # Get PIN and verify
        pin = LoginPin.objects.get(user=user).pin
        response = client.post(reverse("users:verify-pin"), {"email": user.email, "pin": pin})
        # Should redirect to safe default URL
        assert response.status_code == 302
        assert "attacker" not in response.url

        # Check no new user created
        assert User.objects.count() == count

    def test_after_login_url_priority(self, client):
        """Test that after_login_url from the form takes precedence over next parameter."""
        user = UserFactory()

        # Case 1: Test when both after_login_url and next are provided
        response = client.post(
            reverse("users:login") + "?next=/next-param",
            {
                "email": user.email,
                "after_login_url": "/form-after-login",
            },
        )
        assert response.status_code == 302
        # Get PIN and verify to test redirect
        pin = LoginPin.objects.get(user=user).pin
        response = client.post(reverse("users:verify-pin"), {"email": user.email, "pin": pin})
        assert response.status_code == 302
        assert response.url == "/form-after-login"
        mail.outbox.clear()
        LoginPin.objects.all().delete()

        # Case 2: Test when only next parameter is provided
        response = client.post(
            reverse("users:login") + "?next=/next-param",
            {
                "email": user.email,
            },
        )
        assert response.status_code == 302
        # Get PIN and verify to test redirect
        pin = LoginPin.objects.get(user=user).pin
        response = client.post(reverse("users:verify-pin"), {"email": user.email, "pin": pin})
        assert response.status_code == 302
        assert response.url == "/next-param"
        mail.outbox.clear()
        LoginPin.objects.all().delete()

        # Case 3: Test when neither is provided
        response = client.post(
            reverse("users:login"),
            {
                "email": user.email,
            },
        )
        assert response.status_code == 302
        # Get PIN and verify to test redirect
        pin = LoginPin.objects.get(user=user).pin
        response = client.post(reverse("users:verify-pin"), {"email": user.email, "pin": pin})
        assert response.status_code == 302
        assert response.url == "/users/~redirect/"
