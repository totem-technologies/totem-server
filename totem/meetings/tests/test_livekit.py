from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.circles.models import CircleEvent
from totem.circles.tests.factories import CircleEventFactory
from totem.users.models import User


@pytest.mark.django_db
class TestGetLiveKitToken:
    LIVEKIT_PROVIDER_PATH = "totem.meetings.livekit_provider"

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
        event.start = timezone.now() - timedelta(hours=1)
        event.save()

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 403

    def test_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": "non-existent-slug"})
        response = client.get(url)
        assert response.status_code == 404

    def test_get_livekit_token_success(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = CircleEventFactory(start=timezone.now())
        event.attendees.add(user)
        event.joined.add(user)
        event.save()

        with (
            patch(
                f"{self.LIVEKIT_PROVIDER_PATH}.create_access_token", return_value="fake-jwt-token"
            ) as mock_create_token,
            patch(f"{self.LIVEKIT_PROVIDER_PATH}.initialize_room", new_callable=Mock) as mock_init_room,
        ):
            url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
            response = client.get(url)

        assert response.status_code == 200
        assert response.json() == {"token": "fake-jwt-token"}

        # Verify mocks were called correctly
        mock_init_room.assert_called_once()
        mock_create_token.assert_called_once()
        # Ensure correct arguments were passed to the token creation function
        args, _ = mock_create_token.call_args
        assert args[0] == user
        assert args[1] == event

    def test_get_livekit_token_not_joinable(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        # Create an event that started 2 hours ago
        event = CircleEventFactory(start=timezone.now() - timedelta(hours=2))
        event.attendees.add(user)

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 403
        assert response.json() == "Session is not joinable at this time."

    def test_get_livekit_token_not_attendee(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = CircleEventFactory(start=timezone.now())

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 403
        assert response.json() == "Session is not joinable at this time."

    def test_get_livekit_token_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": "non-existent-slug"})
        response = client.get(url)

        assert response.status_code == 404
        assert response.json() == "Session not found"

    def test_pass_totem_success(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = CircleEventFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.pass_totem", new_callable=Mock) as mock_pass_totem:
            url = reverse("mobile-api:pass_totem", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 200
        mock_pass_totem.assert_called_once_with(event.slug, user.slug)

    def test_accept_totem_success(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = CircleEventFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.accept_totem", new_callable=Mock) as mock_accept_totem:
            url = reverse("mobile-api:accept_totem", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 200
        mock_accept_totem.assert_called_once_with(event.slug, user.slug)

    def test_start_room_success_by_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()
        event = CircleEventFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.start_room", new_callable=Mock) as mock_start_room:
            url = reverse("mobile-api:start_room", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 200
        mock_start_room.assert_called_once_with(event.slug)

    def test_start_room_forbidden_for_non_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = CircleEventFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.start_room", new_callable=Mock) as mock_start_room:
            url = reverse("mobile-api:start_room", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 403
        mock_start_room.assert_not_called()

    def test_mute_participant_success_by_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()
        event = CircleEventFactory()
        participant_to_mute = "participant-slug-to-mute"

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.mute_participant", new_callable=Mock) as mock_mute:
            url = reverse(
                "mobile-api:mute_participant",
                kwargs={"event_slug": event.slug, "participant_identity": participant_to_mute},
            )
            response = client.post(url)

        assert response.status_code == 200
        mock_mute.assert_called_once_with(event.slug, participant_to_mute)

    def test_mute_participant_forbidden_for_non_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = CircleEventFactory()
        participant_to_mute = "participant-slug-to-mute"

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.mute_participant", new_callable=Mock) as mock_mute:
            url = reverse(
                "mobile-api:mute_participant",
                kwargs={"event_slug": event.slug, "participant_identity": participant_to_mute},
            )
            response = client.post(url)

        assert response.status_code == 403
        mock_mute.assert_not_called()

    def test_remove_participant_success_by_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        event = CircleEventFactory()
        participant_to_remove = "participant-slug-to-remove"

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.remove_participant", new_callable=Mock) as mock_remove:
            url = reverse(
                "mobile-api:remove_participant",
                kwargs={"event_slug": event.slug, "participant_identity": participant_to_remove},
            )
            response = client.post(url)

        assert response.status_code == 200
        mock_remove.assert_called_once_with(event.slug, participant_to_remove)

    def test_remove_participant_forbidden_for_non_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = CircleEventFactory()
        participant_to_remove = "participant-slug-to-remove"

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.remove_participant", new_callable=Mock) as mock_remove:
            url = reverse(
                "mobile-api:remove_participant",
                kwargs={"event_slug": event.slug, "participant_identity": participant_to_remove},
            )
            response = client.post(url)

        assert response.status_code == 403
        mock_remove.assert_not_called()

    def test_remove_participant_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()
        participant_to_remove = "participant-slug-to-remove"

        url = reverse(
            "mobile-api:remove_participant",
            kwargs={"event_slug": "non-existent-slug", "participant_identity": participant_to_remove},
        )
        response = client.post(url)

        assert response.status_code == 404
