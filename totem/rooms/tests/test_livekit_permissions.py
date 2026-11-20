import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import jwt
import pytest
from django.test import override_settings
from livekit import api

from totem.rooms import livekit

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
    user = SimpleNamespace(slug="user", name="Name")
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
    claims = jwt.decode(
        livekit.create_access_token(SimpleNamespace(slug="user", name=""), "room"), SECRET, algorithms=["HS256"]
    )
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
