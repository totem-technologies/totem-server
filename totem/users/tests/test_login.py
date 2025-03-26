import pytest
from django.core import mail
from django.urls import reverse

from totem.users.models import User
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestLogInView:
    def test_login_new_user(self, client):
        email = "testuser@totem.org"
        with pytest.raises(User.DoesNotExist):
            User.objects.get(email=email)
        response = client.post(reverse("users:login"), {"email": email})
        # Check that the response is a 200
        assert response.status_code == 200
        # Check that an email was sent
        assert len(mail.outbox) == 1
        assert "link" in mail.outbox[0].body
        # Check that a new user was created
        count = User.objects.count()
        assert count == 1
        user = User.objects.get(email=email)
        assert user.email == email
        assert user.newsletter_consent is False

    def test_signup_new_with_consent(self, client):
        assert len(mail.outbox) == 0
        email = "testuserconsent@totem.org"
        with pytest.raises(User.DoesNotExist):
            User.objects.get(email=email)
        response = client.get(reverse("users:signup"))
        assert "newsletter_consent" in response.content.decode()
        client.post(reverse("users:signup"), {"email": email, "newsletter_consent": True})
        # Check that an email was sent
        assert len(mail.outbox) == 1
        user = User.objects.get(email=email)
        assert user.newsletter_consent is True

    def test_login_existing_user(self, client):
        # Create an existing user
        user = UserFactory()
        count = User.objects.count()
        # Submit the login form with an existing email
        response = client.post(reverse("users:login"), {"email": user.email, "name": "Not my name"})
        assert response.status_code == 200
        # Check that an email was sent
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert mail.outbox[0].subject == "Totem sign in link"
        # Check that no new user was created, and the name is not changed
        assert User.objects.count() == count
        assert user.name != "Test User"

    def test_login_failure(self, client):
        # Submit the login form with an invalid email
        response = client.post(reverse("users:login"), {"email": "invalid"})
        # Check that the response is not a redirect to the success URL
        assert b"error" in response.content
        # Check that no email was sent
        assert len(mail.outbox) == 0
        # Check that "check your inbox" in no new
        # assert "check your inbox" in User.objects.count()

    def test_login_parameters(self, client):
        # Create an existing user
        user = UserFactory()
        user.save()
        count = User.objects.count()
        # Submit the login form with an existing email
        response = client.post(
            reverse("users:login"),
            {
                "email": user.email,
                "name": user.name,
                "after_login_url": "/foo",
            },
        )
        assert response.status_code == 200
        # Check that an email was sent
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert mail.outbox[0].subject == "Totem sign in link"
        assert "next=/foo" in mail.outbox[0].body  # type: ignore
        # Check that no new user was created
        assert User.objects.count() == count

    def test_login_parameters_atacker(self, client):
        # Create an existing user
        user = UserFactory()
        user.save()
        count = User.objects.count()
        # Submit the login form with an existing email
        response = client.post(
            reverse("users:login"),
            {
                "email": user.email,
                "name": user.name,
                "after_login_url": "https://attacker.com",
            },
        )
        assert response.status_code == 200
        # Check that an email was sent
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert mail.outbox[0].subject == "Totem sign in link"
        assert "attacker" not in mail.outbox[0].body  # type: ignore
        # Check that no new user was created
        assert User.objects.count() == count

    def test_after_login_url_priority(self, client):
        """Test that after_login_url from the form takes precedence over next parameter."""
        # Create an existing user
        user = UserFactory()

        # Case 1: Test when both after_login_url and next are provided
        response = client.post(
            reverse("users:login") + "?next=/next-param",
            {
                "email": user.email,
                "after_login_url": "/form-after-login",
            },
        )
        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert "next=/form-after-login" in mail.outbox[0].body
        mail.outbox.clear()

        # Case 2: Test when only next parameter is provided
        response = client.post(
            reverse("users:login") + "?next=/next-param",
            {
                "email": user.email,
            },
        )
        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert "next=/next-param" in mail.outbox[0].body
        mail.outbox.clear()

        # Case 3: Test when neither is provided
        response = client.post(
            reverse("users:login"),
            {
                "email": user.email,
            },
        )
        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert "next=/next-param" not in mail.outbox[0].body
        assert "next=/form-after-login" not in mail.outbox[0].body
        # Verify it contains the default redirect
        assert "next=/users/~redirect/" in mail.outbox[0].body
