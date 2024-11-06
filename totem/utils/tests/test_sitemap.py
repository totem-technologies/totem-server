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
