from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from ninja.testing import TestClient

from totem.circles.models import CircleEvent
from totem.circles.tests.factories import CircleEventFactory


@pytest.mark.django_db
class TestGetLiveKitToken:
    def test_success(self, client: TestClient, user_auth_headers):
        user = user_auth_headers["user"]
        event: CircleEvent = CircleEventFactory()
        event.attendees.add(user)
        event.start = timezone.now()  # Make it joinable
        event.save()

        with patch("totem.circles.mobile_api.create_access_token") as mock_create_token:
            mock_create_token.return_value = "fake-jwt-token"
            url = reverse("api-1.0.0:get_livekit_token", kwargs={"event_slug": event.slug})
            response = client.get(url, headers=user_auth_headers["headers"])

        assert response.status_code == 200
        assert response.json()["token"] == "fake-jwt-token"
        mock_create_token.assert_called_once()
        # Verify it was called with the correct user and event
        args, _ = mock_create_token.call_args
        assert args[0] == user
        assert args[1] == event

    def test_not_attendee(self, client: TestClient, user_auth_headers):
        event: CircleEvent = CircleEventFactory()
        event.start = timezone.now()
        event.save()

        url = reverse("api-1.0.0:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url, headers=user_auth_headers["headers"])

        assert response.status_code == 403
        assert response.json() == "You have not RSVP'd for this event."

    def test_not_joinable(self, client: TestClient, user_auth_headers):
        user = user_auth_headers["user"]
        event: CircleEvent = CircleEventFactory()
        event.attendees.add(user)
        # Event is in the future, so not joinable yet
        event.start = timezone.now() + timezone.timedelta(hours=1)
        event.save()

        url = reverse("api-1.0.0:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url, headers=user_auth_headers["headers"])

        assert response.status_code == 403
        assert response.json() == "This event is not currently active or joinable."

    def test_not_found(self, client: TestClient, user_auth_headers):
        url = reverse("api-1.0.0:get_livekit_token", kwargs={"event_slug": "non-existent-slug"})
        response = client.get(url, headers=user_auth_headers["headers"])
        assert response.status_code == 404

    def test_missing_credentials(self, client: TestClient, user_auth_headers, settings):
        settings.LIVEKIT_API_KEY = None
        settings.LIVEKIT_API_SECRET = None
        user = user_auth_headers["user"]
        event: CircleEvent = CircleEventFactory()
        event.attendees.add(user)
        event.start = timezone.now()
        event.save()

        url = reverse("api-1.0.0:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url, headers=user_auth_headers["headers"])

        assert response.status_code == 500

