from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from django.test import override_settings
from livekit import api as livekit_api

from totem.rooms import api as room_api
from totem.rooms import livekit
from totem.rooms.models import (
    AdmissionAttempt,
    AdmissionPermissionSync,
    AdmissionState,
    AttemptStatus,
    Room,
    SessionAdmission,
)
from totem.rooms.schemas import EventRequest, RemoveReason, StartRoomEvent
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory


@override_settings(
    LIVEKIT_API_KEY="test-key-test-key-test-key-test-key",
    LIVEKIT_API_SECRET="test-secret-test-secret-test-secret-test-secret",
)
def test_token_room_capacity():
    token = livekit.create_access_token(SimpleNamespace(slug="user", name="User"), "room")
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["roomConfig"]["maxParticipants"] == 15


def test_presence_is_raw_and_lookup_errors_are_not_empty():
    with patch("totem.rooms.livekit._get_connected_participants", new=AsyncMock(return_value={"waiting", "member"})):
        assert livekit.get_admission_participants("room") == {"waiting", "member"}
    with patch("totem.rooms.livekit._get_connected_participants", new=AsyncMock(side_effect=TimeoutError)):
        with pytest.raises(livekit.LiveKitPermissionError):
            livekit.get_admission_participants("room")


def test_first_join_proceeds_when_livekit_room_does_not_exist():
    user = SimpleNamespace(is_active=True, pk=1, slug="keeper")
    session = MagicMock(slug="room")
    session.attendees.filter.return_value.exists.return_value = True
    session.end.return_value = room_api.timezone.now() + room_api.timezone.timedelta(hours=1)
    response = SimpleNamespace(is_already_present=True)
    missing = livekit_api.TwirpError(code="not_found", msg="room not found", status=404)
    with (
        patch.object(livekit, "_get_connected_participants", new=AsyncMock(side_effect=missing)),
        patch.object(room_api.Room.objects, "filter") as rooms,
        patch("totem.rooms.admission.prepare_admission_join", return_value=response) as prepare,
    ):
        rooms.return_value.first.return_value = SimpleNamespace(keeper="keeper")
        result = room_api._join_with_admission(session, user, None)
    assert result.status_code == 200
    assert prepare.call_args.kwargs["connected"] == set()
    assert not response.is_already_present


def test_admission_presence_internal_error_is_not_empty():
    error = livekit_api.TwirpError(code="internal", msg="unavailable", status=500)
    with patch.object(livekit, "_get_connected_participants", new=AsyncMock(side_effect=error)):
        with pytest.raises(livekit.LiveKitPermissionError, match="unavailable") as exc:
            livekit.get_admission_participants("room")
    assert exc.value.code == "unavailable"


def test_enforced_remove_is_hard_even_when_hint_succeeds():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.room.send_data = AsyncMock()
    client.room.remove_participant = AsyncMock()
    with patch("totem.rooms.livekit._get_api", return_value=client):
        livekit.remove_participant("room", "member", RemoveReason.REMOVE)
    client.room.remove_participant.assert_awaited_once()
    assert client.room.remove_participant.call_args.args[0].revoke_token_ts > 0


def test_reconcile_empty_presence_reaches_state_machine():
    request = SimpleNamespace(user=SimpleNamespace(slug="keeper"))
    room = MagicMock()
    state = MagicMock()
    with (
        patch.object(room_api, "_get_room_and_require_keeper", return_value=room),
        patch.object(room_api, "get_room_participant_sids", return_value={}),
        patch.object(room_api, "apply_event", return_value=state) as apply,
        patch.object(room_api, "publish_state"),
    ):
        room_api.reconcile_room(request, "room")
    assert apply.call_args.kwargs["connected"] == set()
    assert apply.call_args.kwargs["participant_sids"] == {}


def test_event_passes_sid_snapshot_to_state_machine_and_projection():
    request = SimpleNamespace(user=SimpleNamespace(slug="keeper"))
    body = EventRequest(event=StartRoomEvent(), last_seen_version=0)
    sids = {"keeper": "sid-keeper", "waiting": "sid-waiting"}
    with (
        patch.object(room_api, "get_room_participant_sids", return_value=sids),
        patch.object(room_api, "_project_connected", return_value={"keeper"}) as project,
        patch.object(room_api, "apply_event", return_value=SimpleNamespace(current_speaker="keeper")) as apply,
        patch.object(room_api, "publish_state"),
        patch.object(room_api, "mute_all_participants") as mute,
    ):
        room_api.post_event(request, "room", body)
    project.assert_called_once_with("room", set(sids), participant_sids=sids)
    assert apply.call_args.kwargs["connected"] == set(sids)
    assert apply.call_args.kwargs["participant_sids"] == sids
    mute.assert_called_once_with("room", except_identity="keeper", identities={"keeper"})


def test_unknown_presence_rejects_event_without_state_change():
    request = SimpleNamespace(user=SimpleNamespace(slug="keeper"))
    body = EventRequest(event=StartRoomEvent(), last_seen_version=0)
    with (
        patch.object(
            room_api, "get_room_participant_sids", side_effect=livekit.LiveKitPermissionError("timeout", "timeout")
        ),
        patch.object(room_api, "apply_event") as apply,
    ):
        result = room_api.post_event(request, "room", body)
    assert result.status_code == 500
    assert result.value.code == room_api.ErrorCode.LIVEKIT_ERROR
    apply.assert_not_called()


def test_waiting_participant_cannot_be_muted():
    request = SimpleNamespace(user=SimpleNamespace(slug="keeper"))
    with (
        patch.object(room_api, "_get_room_and_require_keeper", return_value=MagicMock()),
        patch.object(room_api, "get_room_participant_sids", return_value={"waiting": "sid-waiting"}),
        patch.object(room_api, "_project_connected", return_value=set()),
        patch.object(room_api, "mute_participant") as mute,
    ):
        result = room_api.mute(request, "room", "waiting")
    assert result.value.code == room_api.ErrorCode.NOT_IN_ROOM
    mute.assert_not_called()


def test_livekit_sid_snapshot_filters_disconnected_and_handles_errors():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.room.list_participants = AsyncMock(
        return_value=SimpleNamespace(
            participants=[
                SimpleNamespace(identity="member", sid="sid-1", state=livekit_api.ParticipantInfo.State.ACTIVE),
                SimpleNamespace(identity="gone", sid="sid-2", state=livekit_api.ParticipantInfo.State.DISCONNECTED),
                SimpleNamespace(identity="no-sid", sid="", state=livekit_api.ParticipantInfo.State.ACTIVE),
            ]
        )
    )
    with patch.object(livekit, "_get_api", return_value=client):
        assert livekit.get_room_participant_sids("room") == {"member": "sid-1"}
        client.room.list_participants.side_effect = livekit_api.TwirpError(
            code="not_found", msg="room not found", status=404
        )
        assert livekit.get_room_participant_sids("room") == {}
        client.room.list_participants.side_effect = TimeoutError()
        with pytest.raises(livekit.LiveKitPermissionError) as exc:
            livekit.get_room_participant_sids("room")
        assert exc.value.code == "timeout"


@pytest.mark.django_db
def test_replaced_connection_cannot_be_muted():
    keeper, member = UserFactory(), UserFactory()
    session = SessionFactory(space__author=keeper, start=room_api.timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, member)
    Room.objects.get_or_create_for_session(session)
    admission = SessionAdmission.objects.create(session=session, user=member, state=AdmissionState.ADMITTED)
    attempt = AdmissionAttempt.objects.create(
        admission=admission,
        request_id=uuid4(),
        attempt_id=uuid4(),
        status=AttemptStatus.ADMITTED,
        expires_at=room_api.timezone.now() + timedelta(minutes=10),
        participant_sid="original-sid",
    )
    AdmissionPermissionSync.objects.create(
        admission=admission,
        desired_admitted=True,
        revision=1,
        applied_revision=1,
        participant_sid=attempt.participant_sid,
    )
    request = SimpleNamespace(user=keeper)
    with (
        patch.object(room_api, "get_room_participant_sids", return_value={member.slug: "replacement-sid"}),
        patch.object(room_api, "mute_participant") as mute,
    ):
        result = room_api.mute(request, session.slug, member.slug)
    assert result.value.code == room_api.ErrorCode.NOT_IN_ROOM
    mute.assert_not_called()
    with (
        patch.object(room_api, "get_room_participant_sids", return_value={member.slug: attempt.participant_sid}),
        patch.object(room_api, "mute_participant") as mute,
    ):
        result = room_api.mute(request, session.slug, member.slug)
    assert result.status_code == 200
    mute.assert_called_once_with(session.slug, member.slug)


def test_join_passes_raw_presence_without_emitting_analytics():
    user = SimpleNamespace(is_active=True, pk=1, slug="member")
    session = MagicMock(slug="room")
    session.attendees.filter.return_value.exists.return_value = True
    session.end.return_value = room_api.timezone.now() + room_api.timezone.timedelta(hours=1)
    response = SimpleNamespace(is_already_present=False)
    with (
        patch.object(room_api, "get_admission_participants", return_value={"member", "waiting"}),
        patch.object(room_api.Room.objects, "filter") as rooms,
        patch("totem.rooms.admission.prepare_admission_join", return_value=response) as prepare,
        patch.object(room_api.analytics, "event_joined") as analytics,
    ):
        rooms.return_value.first.return_value = SimpleNamespace(keeper="keeper")
        room_api._join_with_admission(session, user, None)
    assert prepare.call_args.kwargs["connected"] == {"member", "waiting"}
    assert response.is_already_present
    analytics.assert_not_called()


def test_remove_ban_passes_domain_flag_and_hard_removes():
    keeper = SimpleNamespace(slug="keeper")
    target = SimpleNamespace(slug="member")
    request = SimpleNamespace(user=keeper)
    room = SimpleNamespace(state_version=3)
    with (
        patch.object(room_api, "_get_room_and_require_keeper", return_value=room),
        patch.object(room_api.User.objects, "filter") as users,
        patch("totem.rooms.admission.record_removal") as record,
        patch.object(room_api, "remove_participant") as remove,
        patch.object(room_api.analytics, "user_removed_from_room"),
    ):
        users.return_value.first.return_value = target
        room_api.remove(request, "room", "member", reason=RemoveReason.BAN)
    record.assert_called_once_with("room", keeper, target, expected_room_version=3, ban=True)
    remove.assert_called_once_with("room", "member", reason=RemoveReason.BAN)
