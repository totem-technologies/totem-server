import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.circles.models import Session
from totem.circles.tests.factories import SessionFactory, SpaceFactory
from totem.meetings.livekit_provider import (
    RoomAlreadyEndedError,
    RoomNotFoundError,
)
from totem.meetings.room_state import SessionState, SessionStatus, TotemStatus
from totem.users.models import User


@pytest.mark.django_db
class TestGetLiveKitToken:
    LIVEKIT_PROVIDER_PATH = "totem.meetings.livekit_provider"

    def test_not_attendee(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event: Session = SessionFactory()
        event.start = timezone.now()
        event.save()

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 403

    def test_not_joinable(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event: Session = SessionFactory()
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
        event = SessionFactory(start=timezone.now())
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
        event = SessionFactory(start=timezone.now() - timedelta(hours=2))
        event.attendees.add(user)

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 403
        assert response.json() == {"error": "Session is not joinable at this time."}

    def test_get_livekit_token_not_attendee(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(start=timezone.now())

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 403
        assert response.json() == {"error": "Session is not joinable at this time."}

    def test_get_livekit_token_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": "non-existent-slug"})
        response = client.get(url)

        assert response.status_code == 404
        assert response.json() == {"error": "Session not found"}

    def test_pass_totem_success(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.pass_totem", new_callable=Mock) as mock_pass_totem:
            url = reverse("mobile-api:pass_totem", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 200
        mock_pass_totem.assert_called_once_with(event.slug, event.space.author.slug, user.slug)

    def test_accept_totem_success(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.accept_totem", new_callable=Mock) as mock_accept_totem:
            url = reverse("mobile-api:accept_totem", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 200
        mock_accept_totem.assert_called_once_with(
            room_name=event.slug,
            user_identity=user.slug,
            keeper_slug=event.space.author.slug,
        )

    def test_start_room_success_by_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.start_room", new_callable=Mock) as mock_start_room:
            url = reverse("mobile-api:start_room", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 200
        mock_start_room.assert_called_once_with(
            room_name=event.slug,
            keeper_slug=event.space.author.slug,
        )

    def test_start_room_forbidden_for_non_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.start_room", new_callable=Mock) as mock_start_room:
            url = reverse("mobile-api:start_room", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 403
        mock_start_room.assert_not_called()

    def test_end_room_success_by_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.end_room", new_callable=Mock) as mock_end_room:
            url = reverse("mobile-api:end_room", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 200
        mock_end_room.assert_called_once_with(event.slug)

    def test_end_room_forbidden_for_non_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.end_room", new_callable=Mock) as mock_end_room:
            url = reverse("mobile-api:end_room", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 403
        mock_end_room.assert_not_called()

    def test_mute_participant_success_by_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)
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
        event = SessionFactory()
        participant_to_mute = "participant-slug-to-mute"

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.mute_participant", new_callable=Mock) as mock_mute:
            url = reverse(
                "mobile-api:mute_participant",
                kwargs={"event_slug": event.slug, "participant_identity": participant_to_mute},
            )
            response = client.post(url)

        assert response.status_code == 403
        mock_mute.assert_not_called()

    def test_mute_all_participants_success_by_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.mute_all_participants", new_callable=Mock) as mock_mute_all:
            url = reverse("mobile-api:mute_all_participants", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 200
        mock_mute_all.assert_called_once_with(event.slug, except_identity=user.slug)

    def test_mute_all_participants_forbidden_for_non_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.mute_all_participants", new_callable=Mock) as mock_mute_all:
            url = reverse("mobile-api:mute_all_participants", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 403
        assert response.json() == {"error": "Only the Keeper can mute participants."}
        mock_mute_all.assert_not_called()

    def test_mute_all_participants_event_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user

        url = reverse("mobile-api:mute_all_participants", kwargs={"event_slug": "non-existent-slug"})
        response = client.post(url)

        assert response.status_code == 404

    def test_mute_all_participants_livekit_api_error(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)

        from livekit import api

        with patch(
            f"{self.LIVEKIT_PROVIDER_PATH}.mute_all_participants",
            side_effect=api.TwirpError(code="500", status=1, msg="LiveKit API error"),
        ) as mock_mute_all:
            url = reverse("mobile-api:mute_all_participants", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 500
        assert "Failed to mute all participants" in response.json()["error"]
        mock_mute_all.assert_called_once_with(event.slug, except_identity=user.slug)

    def test_mute_all_participants_unexpected_error(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)

        with patch(
            f"{self.LIVEKIT_PROVIDER_PATH}.mute_all_participants",
            side_effect=ValueError("Unexpected error"),
        ) as mock_mute_all:
            url = reverse("mobile-api:mute_all_participants", kwargs={"event_slug": event.slug})
            response = client.post(url)

        assert response.status_code == 500
        assert response.json() == {"error": "An unexpected error occurred while muting all participants."}
        mock_mute_all.assert_called_once_with(event.slug, except_identity=user.slug)

    def test_remove_participant_success_by_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)
        participant_to_remove = "participant-slug-to-remove"

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.remove_participant", new_callable=Mock) as mock_remove:
            url = reverse(
                "mobile-api:remove_participant",
                kwargs={"event_slug": event.slug, "participant_identity": participant_to_remove},
            )
            response = client.post(url)

        assert response.status_code == 200
        mock_remove.assert_called_once_with(event.slug, participant_to_remove)

    def test_remove_participant_cannot_remove_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)
        participant_to_remove = event.space.author.slug

        url = reverse(
            "mobile-api:remove_participant",
            kwargs={"event_slug": event.slug, "participant_identity": participant_to_remove},
        )
        response = client.post(url)

        assert response.status_code == 403
        assert response.json() == {"error": "Cannot remove the keeper from the room."}

    def test_remove_participant_forbidden_for_non_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()
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

    def test_reorder_participants_success_by_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)
        event.save()

        new_order = ["participant1-slug", "participant2-slug", user.slug]
        payload = {"order": new_order}

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.reorder", new_callable=Mock, return_value=new_order) as mock_reorder:
            url = reverse("mobile-api:reorder_participants", kwargs={"event_slug": event.slug})
            response = client.post(url, data=json.dumps(payload), content_type="application/json")

        assert response.status_code == 200
        mock_reorder.assert_called_once_with(event.slug, new_order)

    def test_reorder_participants_forbidden_for_non_staff(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()
        payload = {"order": ["some-slug"]}

        with patch(
            f"{self.LIVEKIT_PROVIDER_PATH}.reorder", new_callable=Mock, return_value=["some-slug"]
        ) as mock_reorder:
            url = reverse("mobile-api:reorder_participants", kwargs={"event_slug": event.slug})
            response = client.post(url, data=json.dumps(payload), content_type="application/json")

        assert response.status_code == 403
        mock_reorder.assert_not_called()

    def test_reorder_participants_event_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()
        non_existent_slug = "non-existent-reorder-slug"
        payload = {"order": ["some-slug"]}

        url = reverse("mobile-api:reorder_participants", kwargs={"event_slug": non_existent_slug})
        response = client.post(url, data=json.dumps(payload), content_type="application/json")

        assert response.status_code == 404

    def test_reorder_participants_room_already_ended(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)
        new_order = ["invalid-slug"]
        payload = {"order": new_order}

        with patch(
            f"{self.LIVEKIT_PROVIDER_PATH}.reorder",
            side_effect=RoomAlreadyEndedError(f"Room {event.slug} has already ended."),
        ) as mock_reorder:
            url = reverse("mobile-api:reorder_participants", kwargs={"event_slug": event.slug})
            response = client.post(url, data=json.dumps(payload), content_type="application/json")

        assert response.status_code == 400
        assert response.json() == {"error": f"Room {event.slug} has already ended."}
        mock_reorder.assert_called_once_with(event.slug, new_order)

    def test_reorder_participants_room_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user.is_staff = True
        user.save()

        circle = SpaceFactory(author=user)
        event = SessionFactory(circle=circle)
        new_order = ["invalid-slug"]
        payload = {"order": new_order}

        with patch(
            f"{self.LIVEKIT_PROVIDER_PATH}.reorder",
            side_effect=RoomNotFoundError(f"Room {event.slug} does not exist."),
        ) as mock_reorder:
            url = reverse("mobile-api:reorder_participants", kwargs={"event_slug": event.slug})
            response = client.post(url, data=json.dumps(payload), content_type="application/json")

        assert response.status_code == 404
        assert response.json() == {"error": f"Room {event.slug} does not exist."}
        mock_reorder.assert_called_once_with(event.slug, new_order)

    def test_get_room_state_success(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(start=timezone.now())
        event.attendees.add(user)
        event.joined.add(user)
        event.save()

        mock_state = SessionState(
            speaking_order=["user1", "user2", "user3"],
            speaking_now="user1",
            status=SessionStatus.STARTED,
            totem_status=TotemStatus.ACCEPTED,
            keeper_slug="user-1",
        )

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.get_room_state", return_value=mock_state) as mock_get_state:
            url = reverse("mobile-api:get_room_state", kwargs={"event_slug": event.slug})
            response = client.get(url)

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["speaking_order"] == ["user1", "user2", "user3"]
        assert response_data["speaking_now"] == "user1"
        assert response_data["status"] == SessionStatus.STARTED
        assert response_data["totem_status"] == TotemStatus.ACCEPTED
        mock_get_state.assert_called_once_with(event.slug)

    def test_get_room_state_empty_state(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(start=timezone.now())
        event.attendees.add(user)
        event.joined.add(user)
        event.save()

        mock_state = SessionState(
            speaking_order=[],
            speaking_now=None,
            status=SessionStatus.WAITING,
            totem_status=TotemStatus.NONE,
            keeper_slug="",
        )

        with patch(f"{self.LIVEKIT_PROVIDER_PATH}.get_room_state", return_value=mock_state) as mock_get_state:
            url = reverse("mobile-api:get_room_state", kwargs={"event_slug": event.slug})
            response = client.get(url)

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["speaking_order"] == []
        assert response_data["speaking_now"] is None
        assert response_data["status"] == SessionStatus.WAITING
        assert response_data["totem_status"] == TotemStatus.NONE
        mock_get_state.assert_called_once_with(event.slug)

    def test_get_room_state_event_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user

        url = reverse("mobile-api:get_room_state", kwargs={"event_slug": "non-existent-slug"})
        response = client.get(url)

        assert response.status_code == 404

    def test_get_room_state_room_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(start=timezone.now())
        event.attendees.add(user)
        event.joined.add(user)
        event.save()

        with patch(
            f"{self.LIVEKIT_PROVIDER_PATH}.get_room_state",
            side_effect=RoomNotFoundError(f"Room {event.slug} does not exist."),
        ) as mock_get_state:
            url = reverse("mobile-api:get_room_state", kwargs={"event_slug": event.slug})
            response = client.get(url)

        assert response.status_code == 404
        assert response.json() == {"error": f"Room {event.slug} does not exist."}
        mock_get_state.assert_called_once_with(event.slug)

    def test_get_room_state_livekit_api_error(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(start=timezone.now())
        event.attendees.add(user)
        event.joined.add(user)
        event.save()

        from livekit import api

        with patch(
            f"{self.LIVEKIT_PROVIDER_PATH}.get_room_state",
            side_effect=api.TwirpError(code="500", status=1, msg="LiveKit API error"),
        ) as mock_get_state:
            url = reverse("mobile-api:get_room_state", kwargs={"event_slug": event.slug})
            response = client.get(url)

        assert response.status_code == 500
        assert "Failed to retrieve room state" in response.json()["error"]
        mock_get_state.assert_called_once_with(event.slug)
