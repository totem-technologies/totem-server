from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from livekit import api

from totem.meetings.livekit_provider import (
    KeeperNotInRoomError,
    LiveKitConfigurationError,
    NoAudioTrackError,
    NotCurrentSpeakerError,
    ParticipantNotFoundError,
    RoomAlreadyEndedError,
    RoomAlreadyStartedError,
    RoomNotFoundError,
    UnauthorizedError,
)
from totem.meetings.room_state import SessionState, SessionStatus, TotemStatus
from totem.spaces.tests.factories import SessionFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestGetLivekitToken:
    def test_returns_token_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__published=True, open=True, start=timezone.now() + timedelta(minutes=5))
        session.attendees.add(user)

        with (
            patch("totem.meetings.mobile_api.livekit.initialize_room"),
            patch("totem.meetings.mobile_api.livekit.create_access_token", return_value="test-token"),
        ):
            url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": session.slug})
            response = client.get(url)

        assert response.status_code == 200
        assert response.json()["token"] == "test-token"
        assert user in session.joined.all()

    def test_returns_404_when_session_not_found(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": "nonexistent"})
        response = client.get(url)

        assert response.status_code == 404
        assert "Session not found" in response.json()["error"]

    def test_returns_403_when_session_not_joinable(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        session = SessionFactory(space__published=True, open=False)

        url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": session.slug})
        response = client.get(url)

        assert response.status_code == 403
        assert "not joinable" in response.json()["error"]

    def test_returns_500_on_livekit_configuration_error(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__published=True, open=True, start=timezone.now() + timedelta(minutes=5))
        session.attendees.add(user)

        with patch(
            "totem.meetings.mobile_api.livekit.initialize_room",
            side_effect=LiveKitConfigurationError("Config error"),
        ):
            url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": session.slug})
            response = client.get(url)

        assert response.status_code == 500
        assert "not properly configured" in response.json()["error"]

    def test_returns_500_on_twirp_error(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__published=True, open=True, start=timezone.now() + timedelta(minutes=5))
        session.attendees.add(user)

        with patch(
            "totem.meetings.mobile_api.livekit.initialize_room",
            side_effect=api.TwirpError(code="500", status=1, msg="API error"),
        ):
            url = reverse("mobile-api:get_livekit_token", kwargs={"event_slug": session.slug})
            response = client.get(url)

        assert response.status_code == 500
        assert "Failed to create access token" in response.json()["error"]


@pytest.mark.django_db
class TestPassTotem:
    def test_passes_totem_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.pass_totem"):
            url = reverse("mobile-api:pass_totem", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 200

    def test_returns_404_when_room_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.pass_totem", side_effect=RoomNotFoundError("Room not found")):
            url = reverse("mobile-api:pass_totem", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 404
        assert "Room not found" in response.json()["error"]

    def test_returns_403_when_unauthorized(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.pass_totem", side_effect=UnauthorizedError("Unauthorized")):
            url = reverse("mobile-api:pass_totem", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 403
        assert "Unauthorized" in response.json()["error"]


@pytest.mark.django_db
class TestAcceptTotem:
    def test_accepts_totem_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory()

        with patch("totem.meetings.mobile_api.livekit.accept_totem"):
            url = reverse("mobile-api:accept_totem", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 200

    def test_returns_404_when_keeper_not_in_room(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory()

        with patch(
            "totem.meetings.mobile_api.livekit.accept_totem",
            side_effect=KeeperNotInRoomError("Keeper not in room"),
        ):
            url = reverse("mobile-api:accept_totem", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 404
        assert "Keeper not in room" in response.json()["error"]

    def test_returns_403_when_not_next_speaker(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory()

        with patch(
            "totem.meetings.mobile_api.livekit.accept_totem",
            side_effect=NotCurrentSpeakerError("Not next speaker"),
        ):
            url = reverse("mobile-api:accept_totem", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 403
        assert "Not next speaker" in response.json()["error"]


@pytest.mark.django_db
class TestStartRoom:
    def test_starts_room_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.start_room"):
            url = reverse("mobile-api:start_room", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 200

    def test_returns_403_when_not_keeper(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)

        url = reverse("mobile-api:start_room", kwargs={"event_slug": session.slug})
        response = client.post(url)

        assert response.status_code == 403
        assert "Only the Keeper can start the room" in response.json()["error"]

    def test_returns_400_when_already_started(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch(
            "totem.meetings.mobile_api.livekit.start_room",
            side_effect=RoomAlreadyStartedError("Already started"),
        ):
            url = reverse("mobile-api:start_room", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 400
        assert "Already started" in response.json()["error"]

    def test_returns_404_when_keeper_not_in_room(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch(
            "totem.meetings.mobile_api.livekit.start_room", side_effect=KeeperNotInRoomError("Keeper not in room")
        ):
            url = reverse("mobile-api:start_room", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 404
        assert "Keeper not in room" in response.json()["error"]


@pytest.mark.django_db
class TestEndRoom:
    def test_ends_room_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.end_room"):
            url = reverse("mobile-api:end_room", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 200

    def test_returns_403_when_not_keeper(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)

        url = reverse("mobile-api:end_room", kwargs={"event_slug": session.slug})
        response = client.post(url)

        assert response.status_code == 403
        assert "Only the Keeper can end the room" in response.json()["error"]

    def test_returns_400_when_already_ended(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.end_room", side_effect=RoomAlreadyEndedError("Already ended")):
            url = reverse("mobile-api:end_room", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 400
        assert "Already ended" in response.json()["error"]

    def test_returns_404_when_room_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.end_room", side_effect=RoomNotFoundError("Room not found")):
            url = reverse("mobile-api:end_room", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 404
        assert "Room not found" in response.json()["error"]


@pytest.mark.django_db
class TestMuteParticipant:
    def test_mutes_participant_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.mute_participant"):
            url = reverse(
                "mobile-api:mute_participant", kwargs={"event_slug": session.slug, "participant_identity": "user1"}
            )
            response = client.post(url)

        assert response.status_code == 200

    def test_returns_403_when_not_keeper(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)

        url = reverse(
            "mobile-api:mute_participant", kwargs={"event_slug": session.slug, "participant_identity": "user1"}
        )
        response = client.post(url)

        assert response.status_code == 403
        assert "Only the Keeper can mute participants" in response.json()["error"]

    def test_returns_404_when_participant_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch(
            "totem.meetings.mobile_api.livekit.mute_participant",
            side_effect=ParticipantNotFoundError("Participant not found"),
        ):
            url = reverse(
                "mobile-api:mute_participant", kwargs={"event_slug": session.slug, "participant_identity": "user1"}
            )
            response = client.post(url)

        assert response.status_code == 404
        assert "Participant not found" in response.json()["error"]

    def test_returns_404_when_no_audio_track(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch(
            "totem.meetings.mobile_api.livekit.mute_participant", side_effect=NoAudioTrackError("No audio track")
        ):
            url = reverse(
                "mobile-api:mute_participant", kwargs={"event_slug": session.slug, "participant_identity": "user1"}
            )
            response = client.post(url)

        assert response.status_code == 404
        assert "No audio track" in response.json()["error"]


@pytest.mark.django_db
class TestMuteAllParticipants:
    def test_mutes_all_participants_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.mute_all_participants"):
            url = reverse("mobile-api:mute_all_participants", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 200

    def test_returns_403_when_not_keeper(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)

        url = reverse("mobile-api:mute_all_participants", kwargs={"event_slug": session.slug})
        response = client.post(url)

        assert response.status_code == 403
        assert "Only the Keeper can mute participants" in response.json()["error"]

    def test_returns_500_on_api_error(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch(
            "totem.meetings.mobile_api.livekit.mute_all_participants",
            side_effect=api.TwirpError(code="500", status=1, msg="API error"),
        ):
            url = reverse("mobile-api:mute_all_participants", kwargs={"event_slug": session.slug})
            response = client.post(url)

        assert response.status_code == 500
        assert "Failed to mute all participants" in response.json()["error"]


@pytest.mark.django_db
class TestRemoveParticipant:
    def test_removes_participant_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.remove_participant"):
            url = reverse(
                "mobile-api:remove_participant", kwargs={"event_slug": session.slug, "participant_identity": "user1"}
            )
            response = client.post(url)

        assert response.status_code == 200

    def test_returns_403_when_not_keeper(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)

        url = reverse(
            "mobile-api:remove_participant", kwargs={"event_slug": session.slug, "participant_identity": "user1"}
        )
        response = client.post(url)

        assert response.status_code == 403
        assert "Only the Keeper can remove participants" in response.json()["error"]

    def test_returns_403_when_trying_to_remove_keeper(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        url = reverse(
            "mobile-api:remove_participant",
            kwargs={"event_slug": session.slug, "participant_identity": user.slug},
        )
        response = client.post(url)

        assert response.status_code == 403
        assert "Cannot remove the keeper" in response.json()["error"]

    def test_returns_404_when_participant_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch(
            "totem.meetings.mobile_api.livekit.remove_participant",
            side_effect=ParticipantNotFoundError("Participant not found"),
        ):
            url = reverse(
                "mobile-api:remove_participant", kwargs={"event_slug": session.slug, "participant_identity": "user1"}
            )
            response = client.post(url)

        assert response.status_code == 404
        assert "Participant not found" in response.json()["error"]


@pytest.mark.django_db
class TestReorderParticipants:
    def test_reorders_participants_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.reorder", return_value=["keeper", "user1", "user2"]):
            url = reverse("mobile-api:reorder_participants", kwargs={"event_slug": session.slug})
            response = client.post(url, data={"order": ["user2", "user1", "keeper"]}, content_type="application/json")

        assert response.status_code == 200
        assert response.json()["order"] == ["keeper", "user1", "user2"]

    def test_returns_403_when_not_keeper(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        keeper = UserFactory()
        session = SessionFactory(space__author=keeper)

        url = reverse("mobile-api:reorder_participants", kwargs={"event_slug": session.slug})
        response = client.post(url, data={"order": ["user1", "user2"]}, content_type="application/json")

        assert response.status_code == 403
        assert "Only the Keeper can reorder participants" in response.json()["error"]

    def test_returns_400_when_room_ended(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__author=user)

        with patch("totem.meetings.mobile_api.livekit.reorder", side_effect=RoomAlreadyEndedError("Room ended")):
            url = reverse("mobile-api:reorder_participants", kwargs={"event_slug": session.slug})
            response = client.post(url, data={"order": ["user1", "user2"]}, content_type="application/json")

        assert response.status_code == 400
        assert "Room ended" in response.json()["error"]


@pytest.mark.django_db
class TestGetRoomState:
    def test_returns_room_state_successfully(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__published=True, open=True, start=timezone.now() + timedelta(minutes=5))
        session.attendees.add(user)

        mock_state = SessionState(
            keeper_slug="keeper",
            status=SessionStatus.STARTED,
            speaking_order=["keeper", "user1"],
            speaking_now="keeper",
            next_speaker="user1",
            totem_status=TotemStatus.ACCEPTED,
        )

        with patch("totem.meetings.mobile_api.livekit.get_room_state", return_value=mock_state):
            url = reverse("mobile-api:get_room_state", kwargs={"event_slug": session.slug})
            response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["keeper_slug"] == "keeper"
        assert data["status"] == "started"
        assert data["speaking_now"] == "keeper"

    def test_returns_403_when_session_not_joinable(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        session = SessionFactory(space__published=True, open=False)

        url = reverse("mobile-api:get_room_state", kwargs={"event_slug": session.slug})
        response = client.get(url)

        assert response.status_code == 403
        assert "not joinable" in response.json()["error"]

    def test_returns_404_when_room_not_found(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__published=True, open=True, start=timezone.now() + timedelta(minutes=5))
        session.attendees.add(user)

        with patch("totem.meetings.mobile_api.livekit.get_room_state", side_effect=RoomNotFoundError("Room not found")):
            url = reverse("mobile-api:get_room_state", kwargs={"event_slug": session.slug})
            response = client.get(url)

        assert response.status_code == 404
        assert "Room not found" in response.json()["error"]

    def test_returns_500_on_api_error(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        session = SessionFactory(space__published=True, open=True, start=timezone.now() + timedelta(minutes=5))
        session.attendees.add(user)

        with patch(
            "totem.meetings.mobile_api.livekit.get_room_state",
            side_effect=api.TwirpError(code="500", status=1, msg="API error"),
        ):
            url = reverse("mobile-api:get_room_state", kwargs={"event_slug": session.slug})
            response = client.get(url)

        assert response.status_code == 500
        assert "Failed to retrieve room state" in response.json()["error"]
