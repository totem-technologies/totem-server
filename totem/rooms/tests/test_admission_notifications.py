import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit import api

from totem.rooms import livekit


@pytest.fixture
def livekit_api():
    client = MagicMock()
    client.room.send_data = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    with patch.object(livekit, "_get_api", return_value=context) as get_api:
        yield client, get_api


def test_notification_is_reliable_targeted_and_contains_no_decision(livekit_api):
    client, _ = livekit_api

    assert livekit.publish_admission_changed("session", 42, ["keeper", "attendee", "keeper"]) is True

    client.room.send_data.assert_awaited_once()
    packet = client.room.send_data.await_args.args[0]
    assert packet.room == "session"
    assert packet.topic == "totem.admission.v2"
    assert packet.kind == api.DataPacket.Kind.RELIABLE
    assert list(packet.destination_identities) == ["keeper", "attendee"]
    assert json.loads(packet.data) == {"type": "admission.changed", "session_slug": "session", "version": 42}


def test_empty_destinations_never_broadcast(livekit_api):
    _, get_api = livekit_api
    assert livekit.publish_admission_changed("session", 1, []) is True
    get_api.assert_not_called()


def test_missing_room_notification_is_expected_before_first_connection(livekit_api, caplog):
    client, _ = livekit_api
    client.room.send_data.side_effect = api.TwirpError(
        code="not_found", msg="requested room does not exist", status=404
    )
    with caplog.at_level(logging.INFO, logger=livekit.__name__):
        assert livekit.publish_admission_changed("session", 1, ["keeper"]) is False
    assert all(record.levelno < logging.WARNING for record in caplog.records)
    assert any("room" in record.getMessage().lower() for record in caplog.records)


@pytest.mark.parametrize("error", [OSError("offline"), livekit.LiveKitPermissionError("unavailable", "offline")])
def test_notification_failure_is_best_effort(livekit_api, caplog, error):
    client, _ = livekit_api
    client.room.send_data.side_effect = error
    with caplog.at_level(logging.WARNING, logger=livekit.__name__):
        assert livekit.publish_admission_changed("session", 1, ["keeper"]) is False
    assert caplog.records


def test_notification_times_out(livekit_api, caplog):
    client, _ = livekit_api

    async def wait_forever(*args):
        await asyncio.Event().wait()

    client.room.send_data.side_effect = wait_forever
    timeout = asyncio.timeout
    with (
        patch.object(livekit.asyncio, "timeout", side_effect=lambda seconds: timeout(0.01)) as timeout_mock,
        caplog.at_level(logging.WARNING, logger=livekit.__name__),
    ):
        assert livekit.publish_admission_changed("session", 1, ["keeper"]) is False
    timeout_mock.assert_called_once_with(5)
    assert caplog.records
