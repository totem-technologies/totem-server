import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestSitemap:
    def test_sitemap(self, client):
        response = client.get(reverse("sitemaps_index"))
        assert response.status_code == 200
        assert b"spaces" in response.content
        response = client.get(reverse("sitemaps", kwargs={"section": "pages"}))
        assert response.status_code == 200
        assert b"about" in response.content

    def test_hub_pages_listed(self, client):
        # Index pages are the hubs every post, space and session is linked
        # from, so search engines should find them without walking the lists.
        response = client.get(reverse("sitemaps", kwargs={"section": "pages"}))
        content = response.content.decode()
        for name in ("blog:list", "blog:archive", "spaces:list", "spaces:sessions"):
            assert reverse(name) + "<" in content
