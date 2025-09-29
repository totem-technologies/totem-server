from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.circles.models import CircleEvent
from totem.circles.tests.factories import CircleEventFactory
from totem.users.models import User


@pytest.mark.django_db
class TestGetLiveKitToken:
    def test_success(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event: CircleEvent = CircleEventFactory()
        event.attendees.add(user)
        event.start = timezone.now()  # Make it joinable
        event.save()

        # Your patch path might be different, adjust if needed
        with patch("totem.meetings.mobile_api.livekit_create_access_token") as mock_create_token:
            mock_create_token.return_value = "fake-jwt-token"
            url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
            response = client.get(url)

        assert response.status_code == 200
        assert response.json()["token"] == "fake-jwt-token"
        mock_create_token.assert_called_once()
        args, _ = mock_create_token.call_args
        assert args[0] == user
        assert args[1] == event

    def test_not_attendee(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event: CircleEvent = CircleEventFactory()
        event.start = timezone.now()
        event.save()

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 403

    def test_not_joinable(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event: CircleEvent = CircleEventFactory()
        event.attendees.add(user)
        event.start = timezone.now() + timezone.timedelta(hours=1)
        event.save()

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 403

    def test_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": "non-existent-slug"})
        response = client.get(url)
        assert response.status_code == 404
