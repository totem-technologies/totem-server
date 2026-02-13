import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from livekit import api

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
    end_room,
    get_room_state,
    initialize_room,
    is_user_in_room,
    mute_all_participants,
    mute_participant,
    pass_totem,
    remove_participant,
    reorder,
    start_room,
)
from totem.meetings.room_state import SessionStatus, TotemStatus


def _make_room_metadata(**overrides):
    defaults = {
        "keeper_slug": "keeper",
        "status": "started",
        "speaking_order": ["keeper", "user1"],
        "speaking_now": "keeper",
        "next_speaker": "user1",
        "totem_status": "accepted",
    }
    defaults.update(overrides)
    return json.dumps(defaults)


def _make_participant(identity: str, name: str):
    p = Mock()
    p.identity = identity
    p.name = name
    p.tracks = []
    return p


def _make_audio_track(sid: str):
    track = Mock()
    track.type = api.TrackType.AUDIO
    track.sid = sid
    return track


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

        mock_lkapi.room.create_room.assert_called_once()
        call_args = mock_lkapi.room.create_room.call_args[1]["create"]
        assert call_args.name == "test-room"

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

        mock_lkapi.room.create_room.assert_not_called()


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestGetRoomState:
    """Tests for the get_room_state function."""

    def test_retrieves_room_state_successfully(self):
        """Test that get_room_state parses room metadata correctly."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(speaking_order=["keeper", "user1", "user2"])
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[])

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
        mock_room.metadata = _make_room_metadata(
            status="waiting", speaking_now=None, next_speaker=None, totem_status="none"
        )
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "keeper"),
                _make_participant("user1", "user1"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            start_room("test-room", "keeper")

        mock_lkapi.room.update_room_metadata.assert_called_once()
        call_args = mock_lkapi.room.update_room_metadata.call_args[1]["update"]
        metadata = json.loads(call_args.metadata)
        assert metadata["status"] == "started"
        assert metadata["speaking_now"] == "keeper"

    def test_raises_error_when_already_started(self):
        """Test that start_room raises error when room is already started."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(
            speaking_order=["keeper"], speaking_now="keeper", next_speaker="keeper"
        )
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[_make_participant("keeper", "keeper")])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(RoomAlreadyStartedError):
                start_room("test-room", "keeper")

    def test_raises_error_when_keeper_not_in_room(self):
        """Test that start_room raises error when keeper is not in room."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(
            status="waiting", speaking_order=["keeper"], speaking_now=None, next_speaker=None, totem_status="none"
        )
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[_make_participant("user1", "user1")])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(KeeperNotInRoomError):
                start_room("test-room", "keeper")

    def test_mutes_all_participants_except_keeper(self):
        """Test that start_room mutes all participants except the keeper."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(
            status="waiting",
            speaking_order=["keeper", "user1", "user2"],
            speaking_now=None,
            next_speaker=None,
            totem_status="none",
        )
        mock_room.name = "test-room"

        mock_keeper = _make_participant("keeper", "keeper")
        mock_keeper.tracks = [_make_audio_track("keeper-track")]

        mock_user1 = _make_participant("user1", "user1")
        mock_user1.tracks = [_make_audio_track("user1-track")]

        mock_user2 = _make_participant("user2", "user2")
        mock_user2.tracks = [_make_audio_track("user2-track")]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_keeper, mock_user1, mock_user2])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            start_room("test-room", "keeper")

        assert mock_lkapi.room.mute_published_track.call_count == 2
        muted_tracks = [call[0][0].track_sid for call in mock_lkapi.room.mute_published_track.call_args_list]
        assert "user1-track" in muted_tracks
        assert "user2-track" in muted_tracks
        assert "keeper-track" not in muted_tracks


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestPassTotem:
    """Tests for the pass_totem function."""

    def test_speaker_can_pass_totem(self):
        """Test that the current speaker can pass the totem."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "keeper"),
                _make_participant("user1", "user1"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            pass_totem("test-room", "keeper", "keeper")

        mock_lkapi.room.update_room_metadata.assert_called_once()
        call_args = mock_lkapi.room.update_room_metadata.call_args[1]["update"]
        metadata = json.loads(call_args.metadata)
        assert metadata["totem_status"] == "passing"

    def test_keeper_can_always_pass_totem(self):
        """Test that the keeper can pass the totem even if not speaking."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(speaking_now="user1", next_speaker="keeper")
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "keeper"),
                _make_participant("user1", "user1"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            pass_totem("test-room", "keeper", "keeper")

        mock_lkapi.room.update_room_metadata.assert_called_once()

    def test_non_speaker_cannot_pass_totem(self):
        """Test that a non-speaker cannot pass the totem."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(speaking_order=["keeper", "user1", "user2"])
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "keeper"),
                _make_participant("user1", "user1"),
                _make_participant("user2", "user2"),
            ]
        )

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
        mock_room.metadata = _make_room_metadata(totem_status="passing")
        mock_room.name = "test-room"

        mock_keeper = _make_participant("keeper", "keeper")
        mock_keeper.tracks = [_make_audio_track("keeper-track")]

        mock_user1 = _make_participant("user1", "user1")
        mock_user1.tracks = [_make_audio_track("user1-track")]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_keeper, mock_user1])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            accept_totem("test-room", "keeper", "user1")

        mock_lkapi.room.update_room_metadata.assert_called_once()
        call_args = mock_lkapi.room.update_room_metadata.call_args[1]["update"]
        metadata = json.loads(call_args.metadata)
        assert metadata["speaking_now"] == "user1"
        assert metadata["totem_status"] == "accepted"

        assert mock_lkapi.room.mute_published_track.called

    def test_keeper_can_force_accept_totem(self):
        """Test that the keeper can force accept the totem."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(speaking_now="user1", next_speaker="keeper", totem_status="passing")
        mock_room.name = "test-room"

        mock_user1 = _make_participant("user1", "user1")
        mock_user1.tracks = [_make_audio_track("user1-track")]

        mock_keeper = _make_participant("keeper", "keeper")

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_keeper, mock_user1])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            accept_totem("test-room", "keeper", "keeper")

        mock_lkapi.room.update_room_metadata.assert_called_once()

    def test_non_next_speaker_cannot_accept_totem(self):
        """Test that a user who is not the next speaker cannot accept."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(speaking_order=["keeper", "user1", "user2"], totem_status="passing")
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "keeper"),
                _make_participant("user1", "user1"),
                _make_participant("user2", "user2"),
            ]
        )

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
        mock_room.metadata = _make_room_metadata(
            speaking_order=["keeper"], speaking_now="keeper", next_speaker="keeper"
        )
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[_make_participant("keeper", "keeper")])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            end_room("test-room")

        mock_lkapi.room.update_room_metadata.assert_called_once()
        call_args = mock_lkapi.room.update_room_metadata.call_args[1]["update"]
        metadata = json.loads(call_args.metadata)
        assert metadata["status"] == "ended"
        assert metadata["speaking_now"] is None

    def test_raises_error_when_already_ended(self):
        """Test that end_room raises error when room is already ended."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(
            status="ended", speaking_order=["keeper"], speaking_now=None, next_speaker=None, totem_status="none"
        )
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            with pytest.raises(RoomAlreadyEndedError):
                end_room("test-room")


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestReorder:
    def test_reorders_participants_successfully(self):
        """Test that reorder updates the speaking order correctly."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(speaking_order=["keeper", "user1", "user2"])
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "keeper"),
                _make_participant("user1", "user1"),
                _make_participant("user2", "user2"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            new_order = reorder("test-room", ["user2", "user1", "keeper"])

        assert new_order[0] == "keeper"
        assert "user1" in new_order
        assert "user2" in new_order

    def test_filters_disconnected_participants(self):
        """Test that reorder filters out participants not connected to the room."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "keeper"),
                _make_participant("user1", "user1"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            new_order = reorder("test-room", ["user2", "user1", "keeper"])

        assert len(new_order) == 2
        assert "keeper" in new_order
        assert "user1" in new_order
        assert "user2" not in new_order

    def test_raises_error_when_room_ended(self):
        """Test that reorder raises error when room is already ended."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(
            status="ended", speaking_order=["keeper"], speaking_now=None, next_speaker=None, totem_status="none"
        )
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[_make_participant("keeper", "keeper")])

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
        mock_participant = _make_participant("user1", "user1")
        mock_participant.tracks = [_make_audio_track("track-123")]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.get_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            mute_participant("test-room", "user1")

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
        mock_participant = _make_participant("user1", "user1")

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
        mock_participant1 = _make_participant("user1", "user1")
        mock_participant1.tracks = [_make_audio_track("track-1")]

        mock_participant2 = _make_participant("user2", "user2")
        mock_participant2.tracks = [_make_audio_track("track-2")]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_participant1, mock_participant2])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            mute_all_participants("test-room")

        assert mock_lkapi.room.mute_published_track.call_count == 2

    def test_mutes_all_except_specified_identity(self):
        """Test that mute_all_participants skips the except_identity."""
        mock_participant1 = _make_participant("user1", "user1")
        mock_participant1.tracks = [_make_audio_track("track-1")]

        mock_participant2 = _make_participant("keeper", "keeper")
        mock_participant2.tracks = [_make_audio_track("track-2")]

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_participants.return_value = Mock(participants=[mock_participant1, mock_participant2])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            mute_all_participants("test-room", except_identity="keeper")

        assert mock_lkapi.room.mute_published_track.call_count == 1


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestRemoveParticipant:
    """Tests for the remove_participant function."""

    def test_removes_participant_successfully(self):
        """Test that remove_participant removes the correct participant."""
        mock_participant = _make_participant("user1", "user1")

        mock_lkapi = AsyncMock()
        mock_lkapi.room.remove_participant.return_value = mock_participant

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            remove_participant("test-room", "user1")

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


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestSyncParticipantNames:
    """Tests for participant name syncing via slug_to_name."""

    def test_syncs_names_when_they_differ(self):
        """Test that participant names are updated when they differ from the mapping."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "Old Keeper Name"),
                _make_participant("user1", "Old User Name"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            get_room_state("test-room", slug_to_name={"keeper": "New Keeper", "user1": "New User"})

        assert mock_lkapi.room.update_participant.call_count == 2

    def test_no_update_when_names_match(self):
        """Test that no update is called when LiveKit names already match."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "Keeper Name"),
                _make_participant("user1", "User Name"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            get_room_state("test-room", slug_to_name={"keeper": "Keeper Name", "user1": "User Name"})

        mock_lkapi.room.update_participant.assert_not_called()

    def test_skips_participants_not_in_mapping(self):
        """Test that participants not in slug_to_name are skipped."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "Old Name"),
                _make_participant("user1", "Old Name"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            get_room_state("test-room", slug_to_name={"keeper": "New Keeper"})

        assert mock_lkapi.room.update_participant.call_count == 1
        call_args = mock_lkapi.room.update_participant.call_args[0][0]
        assert call_args.identity == "keeper"
        assert call_args.name == "New Keeper"

    def test_uses_anonymous_for_empty_name(self):
        """Test that empty DB name falls back to 'Anonymous'."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[_make_participant("keeper", "Old Name")])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            get_room_state("test-room", slug_to_name={"keeper": ""})

        mock_lkapi.room.update_participant.assert_called_once()
        call_args = mock_lkapi.room.update_participant.call_args[0][0]
        assert call_args.name == "Anonymous"

    def test_no_sync_when_slug_to_name_is_none(self):
        """Test that no sync happens when slug_to_name is not provided."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[_make_participant("keeper", "Any Name")])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            get_room_state("test-room")

        mock_lkapi.room.update_participant.assert_not_called()

    def test_handles_twirp_error_gracefully(self):
        """Test that TwirpError during name sync doesn't crash the operation."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[_make_participant("keeper", "Old Name")])
        mock_lkapi.room.update_participant.side_effect = api.TwirpError(
            code="internal", status=500, msg="Internal error"
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            state = get_room_state("test-room", slug_to_name={"keeper": "New Name"})

        assert state.keeper_slug == "keeper"

    def test_sync_through_start_room(self):
        """Test that name sync works when called through start_room."""
        mock_room = Mock()
        mock_room.metadata = _make_room_metadata(
            status="waiting", speaking_now=None, next_speaker=None, totem_status="none"
        )
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("keeper", "Old Keeper"),
                _make_participant("user1", "Old User"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi
            start_room("test-room", "keeper", slug_to_name={"keeper": "New Keeper", "user1": "New User"})

        assert mock_lkapi.room.update_participant.call_count == 2


@pytest.mark.django_db
@pytest.mark.enable_socket
class TestIsUserInRoom:
    """Tests for the is_user_in_room function."""

    def test_returns_true_when_user_in_room(self):
        """Test that is_user_in_room returns True when user is in the room."""
        mock_room = Mock()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("user1", "User 1"),
                _make_participant("user2", "User 2"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            result = is_user_in_room("test-room", "user1")

        assert result is True

    def test_returns_false_when_user_not_in_room(self):
        """Test that is_user_in_room returns False when user is not in the room."""
        mock_room = Mock()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(
            participants=[
                _make_participant("user1", "User 1"),
            ]
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            result = is_user_in_room("test-room", "user2")

        assert result is False

    def test_returns_false_when_room_not_found(self):
        """Test that is_user_in_room returns False when room doesn't exist."""
        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            result = is_user_in_room("non-existent-room", "user1")

        assert result is False

    def test_returns_false_on_livekit_config_error(self):
        """Test that is_user_in_room returns False when LiveKit is not configured."""
        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            from totem.meetings.livekit_provider import LiveKitConfigurationError

            mock_get_client.return_value.__aenter__.side_effect = LiveKitConfigurationError("Not configured")

            result = is_user_in_room("test-room", "user1")

        assert result is False

    def test_returns_false_on_twirp_error(self):
        """Test that is_user_in_room returns False on API errors."""
        mock_room = Mock()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.side_effect = api.TwirpError(
            code="internal", status=500, msg="Internal error"
        )

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            result = is_user_in_room("test-room", "user1")

        assert result is False

    def test_returns_false_when_room_empty(self):
        """Test that is_user_in_room returns False when room has no participants."""
        mock_room = Mock()
        mock_room.name = "test-room"

        mock_lkapi = AsyncMock()
        mock_lkapi.room.list_rooms.return_value = Mock(rooms=[mock_room])
        mock_lkapi.room.list_participants.return_value = Mock(participants=[])

        with patch("totem.meetings.livekit_provider._get_lk_api_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_lkapi

            result = is_user_in_room("test-room", "user1")

        assert result is False
