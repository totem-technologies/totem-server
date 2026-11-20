import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import jwt
import pytest
from django.test import override_settings
from livekit import api

from totem.rooms import livekit
from totem.rooms.livekit import (
    LiveKitConfigurationError,
    create_access_token,
    disable_camera_participant,
    get_connected_participants,
    mute_all_participants,
    mute_participant,
    remove_participant,
)
from totem.users.models import User
from totem.users.tests.factories import UserFactory

LK_SETTINGS = {
    "LIVEKIT_API_KEY": "test-key-test-key-test-key-test-key-test-key",
    "LIVEKIT_API_SECRET": "test-secret-test-secret-test-secret-test-secret-test-secret",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_track(track_type: api.TrackType, source: api.TrackSource, sid: str) -> MagicMock:
    track = MagicMock()
    track.type = track_type
    track.source = source
    track.sid = sid
    return track


def _make_participant(
    identity: str, has_audio: bool = True, has_video: bool = True, has_screen_share: bool = False
) -> MagicMock:
    participant = MagicMock()
    participant.identity = identity
    tracks: list[MagicMock] = []
    if has_screen_share:
        # Screen-share tracks come first so type-only matching would pick them
        # over the camera/microphone tracks.
        tracks.append(_make_track(api.TrackType.VIDEO, api.TrackSource.SCREEN_SHARE, "track-screen-789"))
        tracks.append(_make_track(api.TrackType.AUDIO, api.TrackSource.SCREEN_SHARE_AUDIO, "track-screen-audio-987"))
    if has_audio:
        tracks.append(_make_track(api.TrackType.AUDIO, api.TrackSource.MICROPHONE, "track-audio-123"))
    if has_video:
        tracks.append(_make_track(api.TrackType.VIDEO, api.TrackSource.CAMERA, "track-video-456"))
    participant.tracks = tracks
    return participant


def _make_mock_lkapi() -> MagicMock:
    mock = MagicMock()
    mock.room.get_participant = AsyncMock()
    mock.room.mute_published_track = AsyncMock()
    mock.room.list_participants = AsyncMock()
    mock.room.remove_participant = AsyncMock()
    # Support async context manager: async with _get_api() as lkapi
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
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
# get_connected_participants
# ---------------------------------------------------------------------------


@pytest.mark.enable_socket
class TestGetConnectedParticipants:
    @override_settings(**LK_SETTINGS)
    def test_excludes_disconnected_participants(self):
        connected = _make_participant("user-1")
        connected.state = api.ParticipantInfo.State.ACTIVE

        disconnected = _make_participant("user-2")
        disconnected.state = api.ParticipantInfo.State.DISCONNECTED

        mock_resp = MagicMock()
        mock_resp.participants = [connected, disconnected]

        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.list_participants.return_value = mock_resp

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            identities = get_connected_participants("room-1")

        assert identities == {"user-1"}

    @override_settings(**LK_SETTINGS)
    def test_returns_empty_set_when_all_disconnected(self):
        disconnected_1 = _make_participant("user-1")
        disconnected_1.state = api.ParticipantInfo.State.DISCONNECTED

        disconnected_2 = _make_participant("user-2")
        disconnected_2.state = api.ParticipantInfo.State.DISCONNECTED

        mock_resp = MagicMock()
        mock_resp.participants = [disconnected_1, disconnected_2]

        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.list_participants.return_value = mock_resp

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            identities = get_connected_participants("room-1")

        assert identities == set()

    @override_settings(**LK_SETTINGS)
    def test_returns_none_when_livekit_unreachable(self):
        with patch(
            "totem.rooms.livekit._get_connected_participants",
            side_effect=api.TwirpError(code="500", status=1, msg="livekit unavailable"),
        ):
            identities = get_connected_participants("room-1")

        assert identities is None


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
    def test_mutes_microphone_not_screen_share_audio(self):
        participant = _make_participant("user-1", has_screen_share=True)
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = participant

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            mute_participant("room-1", "user-1")

        mock_lkapi.room.mute_published_track.assert_called_once()
        req = mock_lkapi.room.mute_published_track.call_args[0][0]
        assert req.track_sid == "track-audio-123"

    @override_settings(**LK_SETTINGS)
    def test_no_audio_track_is_noop(self):
        participant = _make_participant("user-1", has_audio=False)
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = participant

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            mute_participant("room-1", "user-1")

        mock_lkapi.room.mute_published_track.assert_not_called()

    @override_settings(**LK_SETTINGS)
    def test_participant_not_found_is_noop(self):
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = None

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            mute_participant("room-1", "user-1")

        mock_lkapi.room.mute_published_track.assert_not_called()


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

    @override_settings(**LK_SETTINGS)
    def test_skips_screen_share_audio_tracks(self):
        p1 = _make_participant("user-1", has_screen_share=True)
        p2 = _make_participant("user-2")

        mock_resp = MagicMock()
        mock_resp.participants = [p1, p2]

        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.list_participants.return_value = mock_resp

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            mute_all_participants("room-1")

        muted_sids = {call[0][0].track_sid for call in mock_lkapi.room.mute_published_track.call_args_list}
        assert muted_sids == {"track-audio-123"}


# ---------------------------------------------------------------------------
# disable_camera_participant
# ---------------------------------------------------------------------------


@pytest.mark.enable_socket
class TestDisableCameraParticipant:
    @override_settings(**LK_SETTINGS)
    def test_disables_video_track(self):
        participant = _make_participant("user-1")
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = participant

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            disable_camera_participant("room-1", "user-1")

        mock_lkapi.room.mute_published_track.assert_called_once()
        req = mock_lkapi.room.mute_published_track.call_args[0][0]
        assert req.room == "room-1"
        assert req.identity == "user-1"
        assert req.track_sid == "track-video-456"
        assert req.muted is True

    @override_settings(**LK_SETTINGS)
    def test_mutes_camera_not_screen_share(self):
        participant = _make_participant("user-1", has_screen_share=True)
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = participant

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            disable_camera_participant("room-1", "user-1")

        mock_lkapi.room.mute_published_track.assert_called_once()
        req = mock_lkapi.room.mute_published_track.call_args[0][0]
        assert req.track_sid == "track-video-456"

    @override_settings(**LK_SETTINGS)
    def test_no_video_track_is_noop(self):
        participant = _make_participant("user-1", has_video=False)
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = participant

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            disable_camera_participant("room-1", "user-1")

        mock_lkapi.room.mute_published_track.assert_not_called()

    @override_settings(**LK_SETTINGS)
    def test_participant_not_found_is_noop(self):
        mock_lkapi = _make_mock_lkapi()
        mock_lkapi.room.get_participant.return_value = None

        with patch("totem.rooms.livekit.api.LiveKitAPI", return_value=mock_lkapi):
            disable_camera_participant("room-1", "user-1")

        mock_lkapi.room.mute_published_track.assert_not_called()


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
            with pytest.raises(Exception, match="API error"):
                remove_participant("room-1", "user-1")


KEY = "test-key-test-key-test-key-test-key-test-key"
SECRET = "test-secret-test-secret-test-secret-test-secret-test-secret"


def participant(sid="PA_1", *, admitted=True, state=api.ParticipantInfo.ACTIVE):
    return api.ParticipantInfo(
        sid=sid,
        identity="user",
        state=state,
        permission=api.ParticipantPermission(can_publish=admitted, can_subscribe=admitted, can_publish_data=admitted),
    )


def mock_api(*snapshots):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.room.get_participant = AsyncMock(side_effect=list(snapshots))
    client.room.update_participant = AsyncMock()
    client.room.remove_participant = AsyncMock()
    return client


@pytest.mark.parametrize("admitted", [True, False])
@override_settings(LIVEKIT_API_KEY=KEY, LIVEKIT_API_SECRET=SECRET)
def test_token_permission_profiles(admitted):
    user = User(slug="user", name="Name")
    token = livekit.create_access_token(user, "room", admitted=admitted, attributes={"display": "value"})
    claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert claims["sub"] == "user"
    assert claims["name"] == "Name"
    assert claims["attributes"] == {"display": "value"}
    assert claims["exp"] - claims["nbf"] == 60
    assert claims["video"] == {
        "room": "room",
        "roomJoin": True,
        "roomAdmin": False,
        "canPublish": admitted,
        "canSubscribe": admitted,
        "canPublishData": admitted,
        "canUpdateOwnMetadata": False,
        "hidden": False,
    }
    assert claims["roomConfig"]["name"] == "room"
    assert claims["roomConfig"]["emptyTimeout"] == 3600
    assert claims["roomConfig"]["maxParticipants"] == 15


@override_settings(LIVEKIT_API_KEY=KEY, LIVEKIT_API_SECRET=SECRET)
def test_default_token_is_admitted():
    claims = jwt.decode(livekit.create_access_token(User(slug="user", name=""), "room"), SECRET, algorithms=["HS256"])
    assert claims["name"] == "Anonymous"
    assert all(claims["video"][key] for key in ("canPublish", "canSubscribe", "canPublishData"))


@pytest.mark.parametrize("admitted", [True, False])
def test_update_permissions_reads_updates_and_verifies(admitted):
    before = participant(admitted=not admitted)
    after = participant(admitted=admitted)
    client = mock_api(before, after)
    with patch.object(livekit, "_get_api", return_value=client):
        result = livekit.update_participant_permissions(
            "room", "user", admitted=admitted, expected_sid="PA_1", attributes={"label": "value"}
        )
    assert result == after
    assert client.room.get_participant.await_count == 2
    request = client.room.update_participant.await_args.args[0]
    assert (request.room, request.identity, dict(request.attributes)) == ("room", "user", {"label": "value"})
    permission = request.permission
    assert (permission.can_publish, permission.can_subscribe, permission.can_publish_data) == (admitted,) * 3
    assert not any(
        (
            permission.can_update_metadata,
            permission.hidden,
            permission.recorder,
            permission.agent,
            permission.can_subscribe_metrics,
            permission.can_manage_agent_session,
        )
    )
    assert list(permission.can_publish_sources) == []


@pytest.mark.parametrize(
    "before,after,expected,code",
    [
        (participant(state=api.ParticipantInfo.DISCONNECTED), None, None, "participant_missing"),
        (participant(), None, "other", "identity_replaced"),
        (participant(), participant("PA_2"), None, "identity_replaced"),
        (participant(), participant(admitted=False), None, "permission_mismatch"),
    ],
)
def test_update_rejects_stale_or_unverified_participants(before, after, expected, code):
    client = mock_api(before, after)
    with patch.object(livekit, "_get_api", return_value=client), pytest.raises(livekit.LiveKitPermissionError) as exc:
        livekit.update_participant_permissions("room", "user", admitted=True, expected_sid=expected)
    assert exc.value.code == code
    if after is None:
        client.room.update_participant.assert_not_awaited()


@pytest.mark.parametrize(
    "error,code",
    [
        (api.TwirpError(code="not_found", msg="participant not found", status=404), "participant_missing"),
        (api.TwirpError(code="not_found", msg="room not found", status=404), "room_missing"),
        (api.TwirpError(code="not_found", msg="not found", status=404), "participant_missing"),
        (api.TwirpError(code="internal", msg="failure", status=500), "unavailable"),
        (aiohttp.ClientConnectionError("offline"), "unavailable"),
        (asyncio.TimeoutError(), "timeout"),
    ],
)
def test_snapshot_maps_errors(error, code):
    client = mock_api()
    client.room.get_participant.side_effect = error
    with patch.object(livekit, "_get_api", return_value=client), pytest.raises(livekit.LiveKitPermissionError) as exc:
        livekit.get_participant_snapshot("room", "user")
    assert exc.value.code == code


def test_admission_participants_returns_connected_identities():
    client = mock_api()
    client.room.list_participants = AsyncMock(
        return_value=SimpleNamespace(
            participants=[
                participant(),
                api.ParticipantInfo(identity="gone", state=api.ParticipantInfo.DISCONNECTED),
            ]
        )
    )
    with patch.object(livekit, "_get_api", return_value=client):
        assert livekit.get_admission_participants("room") == {"user"}
    assert client.room.list_participants.await_args is not None
    assert client.room.list_participants.await_args.args[0].room == "room"


def test_admission_participants_missing_room_is_empty():
    with patch.object(livekit, "_get_connected_participants", new_callable=AsyncMock) as lookup:
        lookup.side_effect = api.TwirpError(code="not_found", msg="not found", status=404)
        assert livekit.get_admission_participants("room") == set()


@pytest.mark.parametrize(
    "error,code",
    [
        (api.TwirpError(code="internal", msg="failure", status=500), "unavailable"),
        (aiohttp.ClientConnectionError("offline"), "unavailable"),
        (asyncio.TimeoutError(), "timeout"),
        (livekit.LiveKitConfigurationError("not configured"), "unavailable"),
    ],
)
def test_admission_participants_maps_failures(error, code):
    with patch.object(livekit, "_get_connected_participants", new_callable=AsyncMock) as lookup:
        lookup.side_effect = error
        with pytest.raises(livekit.LiveKitPermissionError) as exc:
            livekit.get_admission_participants("room")
    assert exc.value.code == code


def test_admission_participants_bounds_lookup():
    async def slow_lookup(room_name):
        await asyncio.sleep(0.05)
        return set()

    with (
        patch.object(livekit, "_get_connected_participants", side_effect=slow_lookup),
        patch.object(livekit, "PERMISSION_UPDATE_TIMEOUT_SECONDS", 0.01),
        pytest.raises(livekit.LiveKitPermissionError) as exc,
    ):
        livekit.get_admission_participants("room")
    assert exc.value.code == "timeout"


def test_update_timeout_maps_error():
    client = mock_api(participant())
    client.room.update_participant.side_effect = asyncio.TimeoutError()
    with patch.object(livekit, "_get_api", return_value=client), pytest.raises(livekit.LiveKitPermissionError) as exc:
        livekit.update_participant_permissions("room", "user", admitted=True)
    assert exc.value.code == "timeout"


@pytest.mark.parametrize(
    "helper,method",
    [
        (livekit.get_participant_snapshot, "get_participant"),
        (livekit.hard_disconnect_participant, "remove_participant"),
    ],
)
@pytest.mark.parametrize("stage", ["enter", "request", "exit"])
def test_helper_bounds_full_operation(helper, method, stage):
    client = mock_api(participant())

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.05)

    if stage == "enter":
        client.__aenter__.side_effect = slow
    elif stage == "exit":
        client.__aexit__.side_effect = slow
    else:
        getattr(client.room, method).side_effect = slow

    with (
        patch.object(livekit, "_get_api", return_value=client),
        patch.object(livekit, "PERMISSION_UPDATE_TIMEOUT_SECONDS", 0.01),
        pytest.raises(livekit.LiveKitPermissionError) as exc,
    ):
        helper("room", "user")
    assert exc.value.code == "timeout"


@pytest.mark.parametrize(
    "error,code",
    [
        (api.TwirpError(code="not_found", msg="room not found", status=404), "room_missing"),
        (api.TwirpError(code="not_found", msg="participant not found", status=404), "participant_missing"),
        (aiohttp.ClientConnectionError("offline"), "unavailable"),
        (asyncio.TimeoutError(), "timeout"),
    ],
)
def test_hard_disconnect_maps_errors(error, code):
    client = mock_api()
    client.room.remove_participant.side_effect = error
    with patch.object(livekit, "_get_api", return_value=client), pytest.raises(livekit.LiveKitPermissionError) as exc:
        livekit.hard_disconnect_participant("room", "user")
    assert exc.value.code == code


def test_hard_disconnect_uses_revoke_timestamp():
    client = mock_api()
    with (
        patch.object(livekit, "_get_api", return_value=client),
        patch.object(livekit.time, "time", return_value=1234.9),
    ):
        livekit.hard_disconnect_participant("room", "user")
    request = client.room.remove_participant.await_args.args[0]
    assert (request.room, request.identity, request.revoke_token_ts) == ("room", "user", 1234)
    client.room.send_data.assert_not_called()
