from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import override_settings
from livekit import api

from totem.rooms.livekit import (
    LiveKitConfigurationError,
    NoAudioTrackError,
    ParticipantNotFoundError,
    create_access_token,
    mute_all_participants,
    mute_participant,
    remove_participant,
)
from totem.users.tests.factories import UserFactory

LK_SETTINGS = {
    "LIVEKIT_API_KEY": "test-key",
    "LIVEKIT_API_SECRET": "test-secret",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_participant(identity: str, has_audio: bool = True) -> MagicMock:
    participant = MagicMock()
    participant.identity = identity
    if has_audio:
        track = MagicMock()
        track.type = api.TrackType.AUDIO
        track.sid = "track-123"
        participant.tracks = [track]
    else:
        participant.tracks = []
    return participant


def _make_mock_lkapi() -> MagicMock:
    mock = MagicMock()
    mock.room.get_participant = AsyncMock()
    mock.room.mute_published_track = AsyncMock()
    mock.room.list_participants = AsyncMock()
    mock.room.remove_participant = AsyncMock()
    mock.aclose = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# create_access_token
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreateAccessToken:
    @override_settings(**LK_SETTINGS)
    def test_returns_jwt_string(self):
        user = UserFactory()
        session = MagicMock()
        session.slug = "test-session"
        session.attendees.count.return_value = 5

        token = create_access_token(user, session.slug)

        assert isinstance(token, str)
        assert len(token) > 0

    @override_settings(LIVEKIT_API_KEY=None, LIVEKIT_API_SECRET=None)
    def test_raises_when_not_configured(self):
        user = UserFactory()
        session = MagicMock()
        session.slug = "test-session"
        session.attendees.count.return_value = 5

        with pytest.raises(LiveKitConfigurationError):
            create_access_token(user, session.slug)


# ---------------------------------------------------------------------------
# mute_participant
# ---------------------------------------------------------------------------


@pytest.mark.enable_socket
class TestMuteParticipant:
    @override_settings(**LK_SETTINGS)
    def test_mutes_audio_track(self):
        participant = _make_participant("user-1")
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = participant

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            mute_participant("room-1", "user-1")

        mock_lkapi.room.mute_published_track.assert_called_once()
        req = mock_lkapi.room.mute_published_track.call_args[0][0]
        assert req.room == "room-1"
        assert req.identity == "user-1"
        assert req.muted is True

    @override_settings(**LK_SETTINGS)
    def test_raises_on_no_audio_track(self):
        participant = _make_participant("user-1", has_audio=False)
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = participant

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            with pytest.raises(NoAudioTrackError):
                mute_participant("room-1", "user-1")

    @override_settings(**LK_SETTINGS)
    def test_raises_on_participant_not_found(self):
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = None

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            with pytest.raises(ParticipantNotFoundError):
                mute_participant("room-1", "user-1")


# ---------------------------------------------------------------------------
# mute_all_participants
# ---------------------------------------------------------------------------


@pytest.mark.enable_socket
class TestMuteAllParticipants:
    @override_settings(**LK_SETTINGS)
    def test_mutes_all_except_identity(self):
        p1 = _make_participant("user-1")
        p2 = _make_participant("user-2")
        p3 = _make_participant("keeper")

        mock_resp = MagicMock()
        mock_resp.participants = [p1, p2, p3]

        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.list_participants.return_value = mock_resp

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            mute_all_participants("room-1", except_identity="keeper")

        # Should mute user-1 and user-2, skip keeper
        assert mock_lkapi.room.mute_published_track.call_count == 2

    @override_settings(**LK_SETTINGS)
    def test_mutes_all_when_no_exception(self):
        p1 = _make_participant("user-1")
        p2 = _make_participant("user-2")

        mock_resp = MagicMock()
        mock_resp.participants = [p1, p2]

        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.list_participants.return_value = mock_resp

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            mute_all_participants("room-1")

        assert mock_lkapi.room.mute_published_track.call_count == 2


# ---------------------------------------------------------------------------
# remove_participant
# ---------------------------------------------------------------------------


@pytest.mark.enable_socket
class TestRemoveParticipant:
    @override_settings(**LK_SETTINGS)
    def test_removes_participant(self):
        mock_lkapi = _make_mock_lkapi()

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            remove_participant("room-1", "user-1")

        mock_lkapi.room.remove_participant.assert_called_once()

    @override_settings(**LK_SETTINGS)
    def test_raises_on_failure(self):
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.remove_participant.side_effect = Exception("API error")

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            with pytest.raises(ParticipantNotFoundError):
                remove_participant("room-1", "user-1")
