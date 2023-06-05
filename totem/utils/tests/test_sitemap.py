import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestSitemap:
    def test_sitemap(self, client):
        response = client.get(reverse("django.contrib.sitemaps.views.sitemap"))
        assert response.status_code == 200
        assert b"about" in response.content
