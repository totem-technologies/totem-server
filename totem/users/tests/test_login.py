from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class LogInViewTestCase(TestCase):
    fixtures = ["users.yaml"]

    def test_login_success(self):
        # Submit the login form with a valid email
        count = User.objects.count()
        response = self.client.post(reverse("users:login"), {"email": "testuser@example.com"})

        # Check that the response is a redirect to the success URL
        self.assertRedirects(response, reverse("users:login"))

        # Check that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["testuser@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Welcome to ✨Totem✨")

        # Check that a new user was created
        self.assertEqual(User.objects.count(), count + 1)
        assert User.objects.get(email="testuser@example.com")

    def test_login_existing_user(self):
        # Create an existing user
        user = User.objects.get(pk=1)
        count = User.objects.count()

        # Submit the login form with an existing email
        response = self.client.post(reverse("users:login"), {"email": user.email})

        # Check that the response is a redirect to the success URL
        self.assertRedirects(response, reverse("users:login"))

        # Check that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertEqual(mail.outbox[0].subject, "Login to ✨Totem✨")

        # Check that no new user was created
        self.assertEqual(User.objects.count(), count)

    def test_login_failure(self):
        count = User.objects.count()
        # Submit the login form with an invalid email
        response = self.client.post(reverse("users:login"), {"email": "invalid"})

        # Check that the response is not a redirect to the success URL
        assert b"error" in response.content

        # Check that no email was sent
        self.assertEqual(len(mail.outbox), 0)

        # Check that no new user was created
        self.assertEqual(User.objects.count(), count)

    def test_login_parameters(self):
        # Create an existing user
        user = User.objects.get(pk=1)
        count = User.objects.count()

        # Submit the login form with an existing email
        response = self.client.post(
            reverse("users:login"),
            {"email": user.email, "after_login_url": "/foo", "success_url": reverse("pages:home")},
        )

        # Check that the response is a redirect to the success URL
        self.assertRedirects(response, reverse("pages:home"))

        # Check that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertEqual(mail.outbox[0].subject, "Login to ✨Totem✨")
        assert "next=/foo" in mail.outbox[0].body
        # Check that no new user was created
        self.assertEqual(User.objects.count(), count)
