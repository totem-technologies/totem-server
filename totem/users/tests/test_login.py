import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from totem.users.tests.factories import UserFactory

User = get_user_model()


@pytest.mark.django_db
class TestLogInView:
    def test_login_new_user(self, client):
        response = client.post(reverse("users:login"), {"email": "testuser@totem.org"})
        # Check that the response is a redirect to the success URL
        print(response)
        assert response.status_code == 302
        assert response.url == reverse("users:redirect")
        # Check that an email NOT was sent
        assert len(mail.outbox) == 0
        # Check that an email was sent
        # assert len(mail.outbox) == 1
        # assert mail.outbox[0].to == ["testuser@totem.org"]
        # assert mail.outbox[0].subject == "Welcome to ✨Totem✨!"
        # Check that a new user was created
        count = User.objects.count()
        assert count == 1
        assert User.objects.get(email="testuser@totem.org")

    def test_login_existing_user(self, client):
        # Create an existing user
        user = UserFactory()
        count = User.objects.count()
        # Submit the login form with an existing email
        response = client.post(reverse("users:login"), {"email": user.email, "name": "Not my name"})
        # Check that the response is a redirect to the success URL
        assert response.status_code == 302
        assert response.url == reverse("users:login")
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
                "success_url": reverse("pages:home"),
            },
        )
        # Check that the response is a redirect to the success URL
        assert response.status_code == 302
        assert response.url == reverse("pages:home")
        # Check that an email was sent
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert mail.outbox[0].subject == "Totem sign in link"
        assert "next=/foo" in mail.outbox[0].body  # type: ignore
        # Check that no new user was created
        assert User.objects.count() == count
