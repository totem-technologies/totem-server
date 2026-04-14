from django.test import Client, TestCase
from django.urls import reverse

from totem.users.tests.factories import UserFactory

from ..models import Redirect


class TestPages:
    def test_tos(self, client):
        url = reverse("pages:tos")
        response = client.get(url)
        assert response.status_code == 200

    def test_privacy(self, client):
        url = reverse("pages:privacy")
        response = client.get(url)
        assert response.status_code == 200

    def test_about(self, client, proxied_site_mock):
        url = reverse("pages:about")
        response = client.get(url)
        assert response.status_code == 200

    def test_view_how_it_works(self, client, proxied_site_mock):
        url = reverse("pages:how-it-works")
        response = client.get(url)
        assert response.status_code == 200

    def test_team(self, client):
        url = reverse("pages:team")
        response = client.get(url)
        assert response.status_code == 200


class HomeViewTest:
    def test_home(self, client, proxied_site_mock):
        response = client.get(reverse("pages:home"))
        assert response.status_code == 200


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
        resp_url = getattr(response, "url")
        self.assertIn("utm_source=redirect", resp_url)
        self.assertIn("utm_medium=link", resp_url)
        self.assertIn(f"utm_campaign={redirect.slug}", resp_url)
        self.assertTrue(resp_url.startswith(redirect.url))
        redirect.refresh_from_db()
        self.assertEqual(redirect.count, 1)

    def test_redirect_preserves_existing_query_params(self):
        redirect = Redirect.objects.create(slug="withquery", url="https://example.com/page?foo=bar")
        response = self.client.get(reverse("pages:redirect", kwargs={"slug": redirect.slug}))
        resp_url = getattr(response, "url")
        self.assertIn("foo=bar", resp_url)
        self.assertIn(f"utm_campaign={redirect.slug}", resp_url)

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
