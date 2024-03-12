from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from totem.users.tests.factories import UserFactory

from .models import Redirect


class TestPages:
    def test_tos(self, client):
        url = reverse("pages:tos")
        response = client.get(url)
        assert response.status_code == 200

    def test_privacy(self, client):
        url = reverse("pages:privacy")
        response = client.get(url)
        assert response.status_code == 200

    def test_about(self, client):
        mock_content = "<h1>mock content</h1>"
        with patch("totem.pages.webflow.get", return_value=mock_content):
            url = reverse("pages:about")
            response = client.get(url)
            assert response.status_code == 200
            assert response.content.decode("utf-8") == mock_content

    def test_view_how_it_works(self, client):
        # mock .webflow.get to return a string
        mock_content = "<h1>mock content</h1>"
        with patch("totem.pages.webflow.get", return_value=mock_content):
            url = reverse("pages:how-it-works")
            response = client.get(url)
            assert response.status_code == 200
            assert response.content.decode("utf-8") == mock_content

    def test_team(self, client):
        url = reverse("pages:team")
        response = client.get(url)
        assert response.status_code == 200


class HomeViewTest(TestCase):
    def test_home(self):
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Totem")

    def test_home_redirect(self):
        response = self.client.get(reverse("pages:home-redirect"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("pages:home"))
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.get(reverse("pages:home-redirect"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("users:redirect"))
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("users:redirect"))
        # Only actually give the user the marketing home page if they came from Totem.
        response = self.client.get(reverse("pages:home"), headers={"REFERER": settings.EMAIL_BASE_URL})  # type: ignore
        self.assertEqual(response.status_code, 200)


class RedirectViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Set up non-modified objects used by all test methods
        Redirect.objects.create(slug="test", url="https://www.example.com", permanent=True)

    def setUp(self):
        # Every test needs a client.
        self.client = Client()

    def test_redirect(self):
        redirect = Redirect.objects.get(slug="test")
        self.assertEqual(redirect.count, 0)
        response = self.client.get(reverse("pages:redirect", kwargs={"slug": redirect.slug}))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, redirect.url)
        redirect.refresh_from_db()
        self.assertEqual(redirect.count, 1)

    def test_redirect_not_found(self):
        response = self.client.get(reverse("pages:redirect", args=["not-found"]))
        self.assertEqual(response.status_code, 404)

    def test_redirect_qr(self):
        redirect = Redirect.objects.get(slug="test")
        response = self.client.get(reverse("pages:redirect_qr", args=[redirect.slug]))
        self.assertEqual(response.status_code, 302)
        user = UserFactory(is_staff=True)
        self.client.force_login(user)
        redirect = Redirect.objects.get(slug="test")
        response = self.client.get(reverse("pages:redirect_qr", args=[redirect.slug]))
        self.assertEqual(response.status_code, 200)
