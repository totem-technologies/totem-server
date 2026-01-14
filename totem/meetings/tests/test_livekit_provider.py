"""
Unit tests for the livekit_provider module.

These tests mock the internal LiveKit API calls rather than the entire provider functions,
allowing us to test the actual logic inside each function.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from django.conf import settings
from livekit import api

from totem.circles.tests.factories import SessionFactory
from totem.meetings.livekit_provider import (
    KeeperNotInRoomError,
    NoAudioTrackError,
    NotCurrentSpeakerError,
    ParticipantNotFoundError,
    RoomAlreadyEndedError,
    RoomAlreadyStartedError,
    RoomNotFoundError,
    UnauthorizedError,
    accept_totem,
    create_access_token,
    end_room,
    get_room_state,
    initialize_room,
    mute_all_participants,
    mute_participant,
    pass_totem,
    remove_participant,
    reorder,
    start_room,
)
from totem.meetings.room_state import SessionState, SessionStatus, TotemStatus
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestCreateAccessToken:
    """Tests for the create_access_token function."""

    @patch("totem.meetings.livekit_provider._run_async_in_thread")
    def test_creates_valid_token(self, mock_thread):
        """Test that create_access_token generates a valid JWT token."""
        user = UserFactory()
        event = SessionFactory()
        event.attendees.add(user)

        with (
            patch.object(settings, "LIVEKIT_API_KEY", "test-key"),
            patch.object(settings, "LIVEKIT_API_SECRET", "test-secret"),
        ):
            token = create_access_token(user, event)

        assert isinstance(token, str)
        assert len(token) > 0

    @patch("totem.meetings.livekit_provider._run_async_in_thread")
    def test_triggers_background_validation(self, mock_thread):
        """Test that create_access_token triggers background validation."""
        user = UserFactory()
        event = SessionFactory()
        event.attendees.add(user)

        with (
            patch.object(settings, "LIVEKIT_API_KEY", "test-key"),
            patch.object(settings, "LIVEKIT_API_SECRET", "test-secret"),
        ):
            create_access_token(user, event)

        # Verify background task was triggered
        mock_thread.assert_called_once()


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestInitializeRoom:
    """Tests for the initialize_room function."""

    def test_creates_room_when_not_exists(self):
        """Test that initialize_room creates a room when it doesn't exist."""
        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            initialize_room("test-room", ["user1", "user2"], "user1")

        # Verify room was created with correct metadata
        mock_lkapi.room.create_room.assert_called_once()
        call_args = mock_lkapi.room.create_room.call_args[1]["create"]
        assert call_args.name == "test-room"

        # Verify metadata contains the initial state
        metadata = json.loads(call_args.metadata)
        assert metadata["keeper_slug"] == "user1"
        assert metadata["speaking_order"] == ["user1", "user2"]

    def test_does_not_create_room_when_exists(self):
        """Test that initialize_room doesn't create a room if it already exists."""
        mock_room = Mock()
        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            initialize_room("test-room", ["user1", "user2"], "user1")

        # Should not create room if it already exists
        mock_lkapi.room.create_room.assert_not_called()


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestGetRoomState:
    """Tests for the get_room_state function."""

    def test_retrieves_room_state_successfully(self):
        """Test that get_room_state parses room metadata correctly."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper", "user1", "user2"],
                "speaking_now": "keeper",
                "next_speaker": "user1",
                "totem_status": "accepted",
            }
        )

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            state = get_room_state("test-room")

        assert state.keeper_slug == "keeper"
        assert state.status == SessionStatus.STARTED
        assert state.speaking_now == "keeper"
        assert state.next_speaker == "user1"
        assert state.totem_status == TotemStatus.ACCEPTED

    def test_raises_error_when_room_not_found(self):
        """Test that get_room_state raises RoomNotFoundError when room doesn't exist."""
        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(RoomNotFoundError):
                get_room_state("non-existent-room")


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestStartRoom:
    """Tests for the start_room function."""

    def test_starts_room_successfully(self):
        """Test that start_room updates the room state correctly."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "waiting",
                "speaking_order": ["keeper", "user1"],
                "speaking_now": None,
                "next_speaker": None,
                "totem_status": "none",
            }
        )

        mock_participant1 = Mock()
        mock_participant1.identity = "keeper"
        mock_participant2 = Mock()
        mock_participant2.identity = "user1"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = mock_participant1
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_participant1, mock_participant2])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            start_room("test-room", "keeper")

        # Verify metadata was updated
        mock_lkapi.room.update_room_metadata.assert_called_once()
        call_args = mock_lkapi.room.update_room_metadata.call_args[1]["update"]
        metadata = json.loads(call_args.metadata)
        assert metadata["status"] == "started"
        assert metadata["speaking_now"] == "keeper"

    def test_raises_error_when_already_started(self):
        """Test that start_room raises error when room is already started."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper"],
                "speaking_now": "keeper",
                "next_speaker": "keeper",
                "totem_status": "accepted",
            }
        )

        mock_participant = Mock()
        mock_participant.identity = "keeper"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(RoomAlreadyStartedError):
                start_room("test-room", "keeper")

    def test_raises_error_when_keeper_not_in_room(self):
        """Test that start_room raises error when keeper is not in room."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "waiting",
                "speaking_order": ["keeper"],
                "speaking_now": None,
                "next_speaker": None,
                "totem_status": "none",
            }
        )

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = None

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(KeeperNotInRoomError):
                start_room("test-room", "keeper")


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestPassTotem:
    """Tests for the pass_totem function."""

    def test_speaker_can_pass_totem(self):
        """Test that the current speaker can pass the totem."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper", "user1"],
                "speaking_now": "keeper",
                "next_speaker": "user1",
                "totem_status": "accepted",
            }
        )

        mock_participant = Mock()
        mock_participant.identity = "keeper"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            pass_totem("test-room", "keeper", "keeper")

        # Verify metadata was updated with passing status
        mock_lkapi.room.update_room_metadata.assert_called_once()
        call_args = mock_lkapi.room.update_room_metadata.call_args[1]["update"]
        metadata = json.loads(call_args.metadata)
        assert metadata["totem_status"] == "passing"

    def test_keeper_can_always_pass_totem(self):
        """Test that the keeper can pass the totem even if not speaking."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper", "user1"],
                "speaking_now": "user1",
                "next_speaker": "keeper",
                "totem_status": "accepted",
            }
        )

        mock_participant = Mock()
        mock_participant.identity = "keeper"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            # Keeper can pass even though user1 is speaking
            pass_totem("test-room", "keeper", "keeper")

        mock_lkapi.room.update_room_metadata.assert_called_once()

    def test_non_speaker_cannot_pass_totem(self):
        """Test that a non-speaker cannot pass the totem."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper", "user1", "user2"],
                "speaking_now": "keeper",
                "next_speaker": "user1",
                "totem_status": "accepted",
            }
        )

        mock_participant = Mock()
        mock_participant.identity = "keeper"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(UnauthorizedError):
                pass_totem("test-room", "keeper", "user2")


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestAcceptTotem:
    """Tests for the accept_totem function."""

    def test_next_speaker_can_accept_totem(self):
        """Test that the next speaker can accept the totem."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper", "user1"],
                "speaking_now": "keeper",
                "next_speaker": "user1",
                "totem_status": "passing",
            }
        )

        # Mock tracks for keeper
        mock_keeper_track = Mock()
        mock_keeper_track.type = api.TrackType.AUDIO
        mock_keeper_track.sid = "keeper-track"

        mock_keeper = Mock()
        mock_keeper.identity = "keeper"
        mock_keeper.tracks = [mock_keeper_track]

        # Mock tracks for user1
        mock_user1_track = Mock()
        mock_user1_track.type = api.TrackType.AUDIO
        mock_user1_track.sid = "user1-track"

        mock_user1 = Mock()
        mock_user1.identity = "user1"
        mock_user1.tracks = [mock_user1_track]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = mock_keeper
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_keeper, mock_user1])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            accept_totem("test-room", "keeper", "user1")

        # Verify metadata was updated
        mock_lkapi.room.update_room_metadata.assert_called_once()
        call_args = mock_lkapi.room.update_room_metadata.call_args[1]["update"]
        metadata = json.loads(call_args.metadata)
        assert metadata["speaking_now"] == "user1"
        assert metadata["totem_status"] == "accepted"

        # Verify keeper was muted (not user1)
        assert mock_lkapi.room.mute_published_track.called

    def test_keeper_can_force_accept_totem(self):
        """Test that the keeper can force accept the totem."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper", "user1"],
                "speaking_now": "user1",
                "next_speaker": "keeper",
                "totem_status": "passing",
            }
        )

        # Mock user1 track
        mock_user1_track = Mock()
        mock_user1_track.type = api.TrackType.AUDIO
        mock_user1_track.sid = "user1-track"

        mock_user1 = Mock()
        mock_user1.identity = "user1"
        mock_user1.tracks = [mock_user1_track]

        mock_keeper = Mock()
        mock_keeper.identity = "keeper"
        mock_keeper.tracks = []

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = mock_keeper
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_keeper, mock_user1])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            accept_totem("test-room", "keeper", "keeper")

        mock_lkapi.room.update_room_metadata.assert_called_once()

    def test_non_next_speaker_cannot_accept_totem(self):
        """Test that a user who is not the next speaker cannot accept."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper", "user1", "user2"],
                "speaking_now": "keeper",
                "next_speaker": "user1",
                "totem_status": "passing",
            }
        )

        mock_keeper = Mock()
        mock_keeper.identity = "keeper"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.get_participant.return_value = mock_keeper

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(NotCurrentSpeakerError):
                accept_totem("test-room", "keeper", "user2")


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestEndRoom:
    """Tests for the end_room function."""

    def test_ends_room_successfully(self):
        """Test that end_room updates the room state correctly."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper"],
                "speaking_now": "keeper",
                "next_speaker": "keeper",
                "totem_status": "accepted",
            }
        )

        mock_participant = Mock()
        mock_participant.identity = "keeper"
        mock_participant.tracks = []

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_participant])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            end_room("test-room")

        # Verify metadata was updated
        mock_lkapi.room.update_room_metadata.assert_called_once()
        call_args = mock_lkapi.room.update_room_metadata.call_args[1]["update"]
        metadata = json.loads(call_args.metadata)
        assert metadata["status"] == "ended"
        assert metadata["speaking_now"] is None

    def test_raises_error_when_already_ended(self):
        """Test that end_room raises error when room is already ended."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "ended",
                "speaking_order": ["keeper"],
                "speaking_now": None,
                "next_speaker": None,
                "totem_status": "none",
            }
        )

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(RoomAlreadyEndedError):
                end_room("test-room")


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestReorder:
    """Tests for the reorder function."""

    def test_reorders_participants_successfully(self):
        """Test that reorder updates the speaking order correctly."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "started",
                "speaking_order": ["keeper", "user1", "user2"],
                "speaking_now": "keeper",
                "next_speaker": "user1",
                "totem_status": "accepted",
            }
        )

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            new_order = reorder("test-room", ["user2", "user1", "keeper"])

        # Verify keeper is always first
        assert new_order[0] == "keeper"
        assert "user1" in new_order
        assert "user2" in new_order

    def test_raises_error_when_room_ended(self):
        """Test that reorder raises error when room is already ended."""
        mock_room = Mock()
        mock_room.metadata = json.dumps(
            {
                "keeper_slug": "keeper",
                "status": "ended",
                "speaking_order": ["keeper"],
                "speaking_now": None,
                "next_speaker": None,
                "totem_status": "none",
            }
        )

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(RoomAlreadyEndedError):
                reorder("test-room", ["user1", "keeper"])


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestMuteParticipant:
    """Tests for the mute_participant function."""

    def test_mutes_participant_successfully(self):
        """Test that mute_participant mutes the correct participant."""
        mock_track = Mock()
        mock_track.type = api.TrackType.AUDIO
        mock_track.sid = "track-123"

        mock_participant = Mock()
        mock_participant.identity = "user1"
        mock_participant.tracks = [mock_track]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.get_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            mute_participant("test-room", "user1")

        # Verify mute was called
        mock_lkapi.room.mute_published_track.assert_called_once()

    def test_raises_error_when_participant_not_found(self):
        """Test that mute_participant raises error when participant not found."""
        mock_lkapi = AsyncMock()
        mock_lkapi.room.get_participant.return_value = None

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(ParticipantNotFoundError):
                mute_participant("test-room", "non-existent-user")

    def test_raises_error_when_no_audio_track(self):
        """Test that mute_participant raises error when participant has no audio track."""
        mock_participant = Mock()
        mock_participant.identity = "user1"
        mock_participant.tracks = []  # No audio tracks

        mock_lkapi = AsyncMock()
        mock_lkapi.room.get_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(NoAudioTrackError):
                mute_participant("test-room", "user1")


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestMuteAllParticipants:
    """Tests for the mute_all_participants function."""

    def test_mutes_all_participants(self):
        """Test that mute_all_participants mutes all participants."""
        mock_track1 = Mock()
        mock_track1.type = api.TrackType.AUDIO
        mock_track1.sid = "track-1"

        mock_track2 = Mock()
        mock_track2.type = api.TrackType.AUDIO
        mock_track2.sid = "track-2"

        mock_participant1 = Mock()
        mock_participant1.identity = "user1"
        mock_participant1.tracks = [mock_track1]

        mock_participant2 = Mock()
        mock_participant2.identity = "user2"
        mock_participant2.tracks = [mock_track2]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_participant1, mock_participant2])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            mute_all_participants("test-room")

        # Verify both participants were muted
        assert mock_lkapi.room.mute_published_track.call_count == 2

    def test_mutes_all_except_specified_identity(self):
        """Test that mute_all_participants skips the except_identity."""
        mock_track1 = Mock()
        mock_track1.type = api.TrackType.AUDIO
        mock_track1.sid = "track-1"

        mock_track2 = Mock()
        mock_track2.type = api.TrackType.AUDIO
        mock_track2.sid = "track-2"

        mock_participant1 = Mock()
        mock_participant1.identity = "user1"
        mock_participant1.tracks = [mock_track1]

        mock_participant2 = Mock()
        mock_participant2.identity = "keeper"
        mock_participant2.tracks = [mock_track2]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_participant1, mock_participant2])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            mute_all_participants("test-room", except_identity="keeper")

        # Verify only user1 was muted, not keeper
        assert mock_lkapi.room.mute_published_track.call_count == 1


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestRemoveParticipant:
    """Tests for the remove_participant function."""

    def test_removes_participant_successfully(self):
        """Test that remove_participant removes the correct participant."""
        mock_participant = Mock()
        mock_participant.identity = "user1"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.remove_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            remove_participant("test-room", "user1")

        # Verify remove was called with correct parameters
        mock_lkapi.room.remove_participant.assert_called_once()

    def test_raises_error_on_api_failure(self):
        """Test that remove_participant raises error when API call fails."""
        mock_lkapi = AsyncMock()
        mock_lkapi.room.remove_participant.side_effect = api.TwirpError(
            code="not_found", status=404, msg="Participant not found"
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(ParticipantNotFoundError):
                remove_participant("test-room", "non-existent-user")
