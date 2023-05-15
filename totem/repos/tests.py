import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestPages:
    def test_prompts(self, client):
        url = reverse("repos:prompt-list")
        response = client.get(url)
        assert response.status_code == 200
