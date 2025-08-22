import pytest
from django.test import Client
from django.urls import reverse

from totem.users.models import User


@pytest.mark.django_db
class TestMobileApiUsers:
    def test_get_current_user(self, client_with_user: tuple[Client, User]):
        """
        Verify that the endpoint returns the currently authenticated user's data.
        """
        client, user = client_with_user
        url = reverse("mobile-api:user_current")

        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == user.email
        assert data["name"] == user.name
        assert data["sessions_joined"] == user.events_joined.count()

    def test_get_current_user_unauthenticated(self, client: Client):
        """
        Verify that the endpoint returns a 401 Unauthorized error for unauthenticated users.
        """
        url = reverse("mobile-api:user_current")
        response = client.get(url)
        assert response.status_code == 401
