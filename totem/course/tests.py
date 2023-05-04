from django.test import TestCase
from django.urls import reverse
import pytest


@pytest.mark.django_db
class TestPages:
    def test_course(self, client, db):
        url = reverse("course:list")
        response = client.get(url)
        assert response.status_code == 200
