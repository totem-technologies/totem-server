from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from django.db import close_old_connections, connection, transaction
from django.http import HttpRequest
from django.test import Client, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from livekit import api
from livekit import api as livekit_api

from totem.api.auth import generate_jwt_token
from totem.rooms import admission
from totem.rooms import api as room_api
from totem.rooms import livekit as room_livekit
from totem.rooms.livekit import LiveKitConfigurationError, LiveKitPermissionError
from totem.rooms.models import (
    AdmissionAttempt,
    AdmissionCommand,
    AdmissionPermissionSync,
    AdmissionState,
    AttemptStatus,
    Room,
    SessionAdmission,
)
from totem.rooms.schemas import (
    BanParticipantEvent,
    ErrorCode,
    EventRequest,
    RemoveReason,
    RoomStatus,
    StartRoomEvent,
    TransitionError,
    UnbanParticipantEvent,
)
from totem.rooms.state_machine import apply_event, record_join
from totem.rooms.tasks import _end_session, end_sessions_without_keeper
from totem.spaces.models import Space
from totem.spaces.tests.factories import SessionFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory

BASE = "/api/mobile/protected/rooms"


@pytest.fixture
def context(client_with_user):
    client, user = client_with_user
    keeper = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    keeper_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(keeper)}")
    return client, user, keeper_client, keeper, session, room


@pytest.fixture
def livekit():
    def participant(room_name, identity):
        assert not connection.in_atomic_block
        return api.ParticipantInfo(
            identity=identity,
            sid=f"sid-{identity}",
            permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
        )

    def update(*args, **kwargs):
        assert not connection.in_atomic_block
        return participant(args[0], args[1])

    with (
        patch("totem.rooms.admission.http.get_admission_participants", return_value=set(), create=True) as presence,
        patch("totem.rooms.admission.http.get_participant_snapshot", side_effect=participant, create=True),
        patch("totem.rooms.admission.permissions.get_participant_snapshot", side_effect=participant),
        patch("totem.rooms.admission.permissions.update_participant_permissions", side_effect=update),
        patch("totem.rooms.admission.permissions.hard_disconnect_participant"),
        patch("totem.rooms.state_machine.publish_state"),
    ):
        yield presence


@pytest.mark.django_db(transaction=True)
def test_request_then_me_returns_own_pending_attempt(client_with_user, livekit):
    client, user = client_with_user
    keeper = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, user)
    Room.objects.get_or_create_for_session(session)
    url = f"/api/mobile/protected/rooms/{session.slug}/admission"
    ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}

    response = client.post(f"{url}/request", data=ids, content_type="application/json")
    assert response.status_code == 200, response.content
    me = client.get(f"{url}/me")
    assert me.status_code == 200, me.content
    assert me.json()["me"]["identity"] == user.slug
    assert me.json()["me"]["request_id"] == ids["request_id"]
    assert me.json()["me"]["attempt_id"] == ids["attempt_id"]
    assert me.json()["me"]["status"] == "pending"
    assert "participants" not in me.json()
    assert "waiting" not in me.json()
    assert "requests" not in me.json()


def post(client, url, body):
    return client.post(url, data=body, content_type="application/json")


def endpoint_cases():
    ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
    decision = {**ids, "command_id": str(uuid4()), "expected_version": 0, "expected_room_version": 0}
    membership = {"command_id": str(uuid4()), "expected_version": 0, "expected_room_version": 0}
    return [
        ("post", "/request", ids, False),
        ("get", "", None, True),
        ("get", "/me", None, False),
        ("post", "/admit-all", {"command_id": str(uuid4()), "expected_room_version": 0}, True),
        ("post", "/activated", {**ids, "expected_version": 0}, False),
        ("post", "/cancel", {**ids, "expected_version": 0}, False),
        (
            "patch",
            "/settings",
            {
                "command_id": str(uuid4()),
                "approval_required": False,
                "expected_revision": 0,
                "expected_room_version": 0,
            },
            True,
        ),
        ("post", "/target/approve", decision, True),
        ("post", "/target/decline", decision, True),
        ("post", "/target/allow", membership, True),
        ("post", "/target/revoke", membership, True),
    ]


def send(client, method, url, body):
    if body is None:
        return client.get(url)
    return getattr(client, method)(url, data=body, content_type="application/json")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("method,suffix,body,keeper_only", endpoint_cases())
def test_unauthenticated_endpoints(context, method, suffix, body, keeper_only):
    _, _, _, _, session, _ = context
    url = f"{BASE}/{session.slug}/admission{suffix}"
    response = send(Client(), method, url, body)
    assert response.status_code == 401


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("method,suffix,body,keeper_only", [case for case in endpoint_cases() if case[3]])
def test_keeper_endpoints_reject_non_keeper(context, livekit, method, suffix, body, keeper_only):
    client, _, _, _, session, _ = context
    response = send(client, method, f"{BASE}/{session.slug}/admission{suffix}", body)
    assert response.status_code == 403, response.content


def request_attempt(context):
    client, _, _, _, session, _ = context
    ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
    response = post(client, f"{BASE}/{session.slug}/admission/request", ids)
    assert response.status_code == 200, response.content
    return ids, response.json()["me"]


def decision_body(room, ids, attempt, command_id=None):
    room.refresh_from_db()
    return {
        **ids,
        "command_id": command_id or str(uuid4()),
        "expected_version": attempt["attempt_version"],
        "expected_room_version": room.state_version,
    }


@pytest.mark.django_db(transaction=True)
def test_snapshot_recovers_queue_and_survives_keeper_reassignment(context, livekit):
    _, user, keeper_client, _, session, room = context
    ids, _ = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    snapshot = keeper_client.get(url)
    assert snapshot.status_code == 200, snapshot.content
    assert any(p["identity"] == user.slug and p["request_id"] == ids["request_id"] for p in snapshot.json()["waiting"])
    replacement = UserFactory()
    session.attendees.add(replacement)
    room.keeper = replacement.slug
    room.save(update_fields=["keeper"])
    assert keeper_client.get(url).status_code == 403
    new_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(replacement)}")
    recovered = new_client.get(url)
    assert recovered.status_code == 200, recovered.content
    assert any(p["request_id"] == ids["request_id"] for p in recovered.json()["waiting"])


@pytest.mark.django_db(transaction=True)
def test_approval_replay_does_not_reverse_later_revoke_and_requires_current_keeper(context, livekit):
    _, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    body = decision_body(room, ids, attempt)
    first = post(keeper_client, f"{url}/{user.slug}/approve", body)
    assert first.status_code == 200, first.content
    membership = SessionAdmission.objects.get(session=session, user=user)
    room.refresh_from_db()
    revoke = post(
        keeper_client,
        f"{url}/{user.slug}/revoke",
        {
            "command_id": str(uuid4()),
            "expected_version": membership.version,
            "expected_room_version": room.state_version,
        },
    )
    assert revoke.status_code == 200, revoke.content
    replay = post(keeper_client, f"{url}/{user.slug}/approve", body)
    assert replay.status_code == 200, replay.content
    assert replay.json()["replayed"] is True
    membership.refresh_from_db()
    assert membership.state == AdmissionState.REVOKED
    room.keeper = user.slug
    room.save(update_fields=["keeper"])
    assert post(keeper_client, f"{url}/{user.slug}/approve", body).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_same_command_id_with_changed_target_or_body_conflicts(context, livekit):
    _, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    body = decision_body(room, ids, attempt)
    assert post(keeper_client, f"{url}/{user.slug}/approve", body).status_code == 200
    assert (
        post(
            keeper_client, f"{url}/{user.slug}/approve", {**body, "expected_version": body["expected_version"] + 1}
        ).status_code
        == 409
    )
    other = UserFactory()
    assert post(keeper_client, f"{url}/{other.slug}/approve", body).status_code == 409
    assert post(keeper_client, f"{url}/{user.slug}/decline", body).status_code == 409


@pytest.mark.django_db(transaction=True)
def test_stale_attempt_version_rejects_rapid_second_decision(context, livekit):
    _, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission/{user.slug}"
    body = decision_body(room, ids, attempt)
    assert post(keeper_client, f"{url}/approve", body).status_code == 200
    response = post(keeper_client, f"{url}/decline", {**body, "command_id": str(uuid4())})
    assert response.status_code == 409
    assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.ADMITTED


@pytest.mark.django_db(transaction=True)
def test_cancel_then_stale_approval_cannot_admit(context, livekit):
    client, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    decision = decision_body(room, ids, attempt)
    cancelled = post(client, f"{url}/cancel", {**ids, "expected_version": attempt["attempt_version"]})
    assert cancelled.status_code == 200, cancelled.content
    assert post(keeper_client, f"{url}/{user.slug}/approve", decision).status_code == 409
    assert SessionAdmission.objects.get(session=session, user=user).state != AdmissionState.ADMITTED


@pytest.mark.django_db(transaction=True)
def test_presence_failure_preserves_snapshot_and_private_me(context, livekit):
    client, user, keeper_client, _, session, _ = context
    request_attempt(context)
    livekit.side_effect = LiveKitPermissionError("unavailable", "presence unavailable")
    url = f"{BASE}/{session.slug}/admission"
    for response in (client.get(f"{url}/me"), keeper_client.get(url)):
        assert response.status_code == 200, response.content
        assert response.json()["connected_count"] is None
        assert response.json()["presence_error"]
    data = client.get(f"{url}/me").json()
    assert data["me"]["identity"] == user.slug
    assert not {"participants", "waiting", "requests"} & data.keys()


@pytest.mark.django_db(transaction=True)
def test_decision_cannot_target_another_sessions_attempt(context, livekit):
    _, user, keeper_client, keeper, session, room = context
    other = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    other.attendees.add(keeper, user)
    Room.objects.get_or_create_for_session(other)
    attempt = admission.request_admission(other.slug, user, uuid4(), uuid4())
    body = {
        "command_id": str(uuid4()),
        "request_id": str(attempt.request_id),
        "attempt_id": str(attempt.attempt_id),
        "expected_version": attempt.version,
        "expected_room_version": room.state_version,
    }
    response = post(keeper_client, f"{BASE}/{session.slug}/admission/{user.slug}/approve", body)
    assert response.status_code in (404, 409)
    attempt.refresh_from_db()
    assert attempt.status == "pending"


@pytest.mark.django_db(transaction=True)
def test_activation_requires_connected_receipt(context, livekit):
    client, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
    assert approved.status_code == 200, approved.content
    current = client.get(f"{url}/me").json()["me"]
    response = post(client, f"{url}/activated", {**ids, "expected_version": current["attempt_version"]})
    assert response.status_code == 409
    assert response.json()["code"] == "connection_required"


@pytest.mark.django_db(transaction=True)
def test_connected_receipt_requires_matching_identity(context, livekit):
    client, _, _, _, session, _ = context
    ids, _ = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission/request"
    livekit.return_value = {"somebody-else"}
    with patch(
        "totem.rooms.admission.http.get_participant_snapshot",
        return_value=api.ParticipantInfo(identity="somebody-else", sid="foreign"),
        create=True,
    ):
        response = post(client, url, {**ids, "connected": True})
    assert response.status_code in (409, 503, 504)
    attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
    assert attempt.connected_at is None


@pytest.mark.django_db(transaction=True)
def test_waiting_and_connected_counts_are_distinct(context, livekit):
    _, user, keeper_client, _, session, _ = context
    request_attempt(context)
    livekit.return_value = {user.slug}
    response = keeper_client.get(f"{BASE}/{session.slug}/admission")
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["connected_count"] == 1
    assert data["pending_count"] == 1
    assert data["admitted_count"] == 0
    assert data["activated_count"] == 0
    assert any(p["identity"] == user.slug for p in data["waiting"])


@pytest.mark.django_db(transaction=True)
def test_toggle_off_promotes_waiter_and_toggle_on_does_not_revoke(context, livekit):
    _, user, keeper_client, _, session, room = context
    request_attempt(context)
    url = f"{BASE}/{session.slug}/admission/settings"
    room.refresh_from_db()
    body = {
        "command_id": str(uuid4()),
        "approval_required": False,
        "expected_revision": room.admission_revision,
        "expected_room_version": room.state_version,
    }
    response = send(keeper_client, "patch", url, body)
    assert response.status_code == 200, response.content
    assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.ADMITTED
    room.refresh_from_db()
    response = send(
        keeper_client,
        "patch",
        url,
        {
            **body,
            "command_id": str(uuid4()),
            "approval_required": True,
            "expected_revision": room.admission_revision,
            "expected_room_version": room.state_version,
        },
    )
    assert response.status_code == 200, response.content
    assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.ADMITTED


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("nested", [False, True])
def test_connection_receipt_reconciles_once_and_same_sid_retries(context, livekit, nested):
    from totem.rooms.admission.http import confirm_connection

    _, user, _, _, session, _ = context
    ids, _ = request_attempt(context)
    attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
    args = (session.slug, user, UUID(ids["request_id"]), UUID(ids["attempt_id"]))
    participant = api.ParticipantInfo(identity=user.slug, sid="new-sid")
    with (
        patch("totem.rooms.admission.http.get_participant_snapshot", return_value=participant),
        patch("totem.rooms.admission.permissions.reconcile_admission_permissions") as reconcile,
        patch("totem.rooms.admission.http.reconcile_admission_permissions", new=reconcile),
    ):
        if nested:
            with transaction.atomic():
                confirm_connection(*args)
                reconcile.assert_not_called()
            reconcile.assert_called_once_with(attempt.admission_id)
        else:
            confirm_connection(*args)
            reconcile.assert_called_once_with(attempt.admission_id)

        reconcile.reset_mock()
        confirm_connection(*args)
        reconcile.assert_called_once_with(attempt.admission_id)
        attempt.refresh_from_db()
        assert attempt.participant_sid == "new-sid"


@pytest.mark.django_db(transaction=True)
def test_connected_receipt_activation_and_duplicate_are_idempotent(context, livekit):
    client, user, keeper_client, _, session, room = context
    url = f"{BASE}/{session.slug}/admission"
    ids, attempt = request_attempt(context)
    initial_version = client.get(f"{url}/me").json()["version"]
    livekit.return_value = {user.slug}
    connected = post(client, f"{url}/request", {**ids, "connected": True})
    assert connected.status_code == 200, connected.content
    assert connected.json()["me"]["connected_at"] is not None
    assert connected.json()["activated_count"] == 0
    assert connected.json()["version"] > initial_version
    attempt = connected.json()["me"]
    approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
    assert approved.status_code == 200, approved.content
    assert approved.json()["snapshot"]["activated_count"] == 0
    assert approved.json()["snapshot"]["version"] > connected.json()["version"]
    current = client.get(f"{url}/me").json()["me"]
    receipt = {**ids, "expected_version": current["attempt_version"]}
    activated = post(client, f"{url}/activated", receipt)
    assert activated.status_code == 200, activated.content
    data = activated.json()
    assert data["me"]["status"] == "activated"
    assert data["activated_count"] == 1
    assert data["version"] > approved.json()["snapshot"]["version"]
    duplicate = post(client, f"{url}/activated", receipt)
    assert duplicate.status_code == 200, duplicate.content
    assert duplicate.json()["activated_count"] == 1
    assert duplicate.json()["version"] == data["version"]
    assert duplicate.json()["me"]["activated_at"] == data["me"]["activated_at"]
    assert session.joined.filter(pk=user.pk).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("code", ["participant_missing", "disconnected"])
def test_failed_connection_receipt_keeps_waiter_in_queue(context, livekit, code):
    client, user, keeper_client, _, session, _ = context
    ids, _ = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    with patch("totem.rooms.admission.http.get_participant_snapshot", side_effect=LiveKitPermissionError(code, code)):
        response = post(client, f"{url}/request", {**ids, "connected": True})
    assert response.status_code == 409
    assert response.json()["code"] == code
    attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
    assert attempt.connected_at is None
    snapshot = keeper_client.get(url)
    assert snapshot.status_code == 200
    assert any(p["identity"] == user.slug and p["request_id"] == ids["request_id"] for p in snapshot.json()["waiting"])


@pytest.mark.django_db(transaction=True)
def test_reconnection_receipt_replaces_sid_and_allows_activation(context, livekit):
    client, user, keeper_client, _, session, room = context
    ids, _ = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    livekit.return_value = {user.slug}
    first = post(client, f"{url}/request", {**ids, "connected": True})
    assert first.status_code == 200, first.content
    approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, first.json()["me"]))
    assert approved.status_code == 200, approved.content

    def replacement(room_name, identity):
        assert not connection.in_atomic_block
        return api.ParticipantInfo(
            identity=identity,
            sid="replacement-sid",
            permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
        )

    with (
        patch("totem.rooms.admission.http.get_participant_snapshot", side_effect=replacement),
        patch("totem.rooms.admission.permissions.get_participant_snapshot", side_effect=replacement),
        patch(
            "totem.rooms.admission.permissions.update_participant_permissions",
            side_effect=lambda room_name, identity, **kwargs: replacement(room_name, identity),
        ),
    ):
        reconnected = post(client, f"{url}/request", {**ids, "connected": True})
        assert reconnected.status_code == 200, reconnected.content
        assert reconnected.json()["me"]["attempt_version"] > first.json()["me"]["attempt_version"]
        assert AdmissionAttempt.objects.get(request_id=ids["request_id"]).participant_sid == "replacement-sid"
        activated = post(
            client, f"{url}/activated", {**ids, "expected_version": reconnected.json()["me"]["attempt_version"]}
        )
        assert activated.status_code == 200, activated.content
        assert activated.json()["me"]["status"] == "activated"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("action", ["admit-all", "settings"])
def test_batch_permission_timeout_is_partial_and_durable(context, livekit, action):
    client, user, keeper_client, _, session, room = context
    request_attempt(context)
    other = UserFactory()
    session.attendees.add(other)
    other_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(other)}")
    ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
    url = f"{BASE}/{session.slug}/admission"
    assert post(other_client, f"{url}/request", ids).status_code == 200

    def update(room_name, identity, **kwargs):
        assert not connection.in_atomic_block
        if identity == user.slug and kwargs["admitted"]:
            raise LiveKitPermissionError("timeout", "update timed out")
        return api.ParticipantInfo(
            identity=identity,
            sid=f"sid-{identity}",
            permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
        )

    room.refresh_from_db()
    body = {"command_id": str(uuid4()), "expected_room_version": room.state_version}
    with patch("totem.rooms.admission.permissions.update_participant_permissions", side_effect=update):
        if action == "settings":
            response = send(
                keeper_client,
                "patch",
                f"{url}/settings",
                {**body, "approval_required": False, "expected_revision": room.admission_revision},
            )
        else:
            response = post(keeper_client, f"{url}/admit-all", body)
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["partial_failure"] is True
    results = {row["identity"]: row for row in data["results"]}
    assert results[user.slug]["participant"]["permission_status"] == "error"
    assert results[user.slug]["participant"]["last_error"] == "timeout"
    assert results[other.slug]["participant"]["permission_status"] == "applied"
    assert results[other.slug]["participant"]["last_error"] is None
    assert {row["identity"] for row in data["snapshot"]["participants"]} >= {user.slug, other.slug}
    sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
    assert sync.applied_revision != sync.revision
    assert sync.retry_count > 0
    assert sync.next_retry_at is not None
    assert SessionAdmission.objects.get(session=session, user=other).state == AdmissionState.ADMITTED


@pytest.mark.django_db(transaction=True)
def test_permanent_decline_allow_does_not_admit_or_replay_decline(context, livekit):
    client, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    body = {**decision_body(room, ids, attempt), "permanent": True}
    declined = post(keeper_client, f"{url}/{user.slug}/decline", body)
    assert declined.status_code == 200, declined.content
    membership = SessionAdmission.objects.get(session=session, user=user)
    assert membership.state == AdmissionState.PERMANENTLY_DECLINED
    room.refresh_from_db()
    allowed = post(
        keeper_client,
        f"{url}/{user.slug}/allow",
        {
            "command_id": str(uuid4()),
            "expected_version": membership.version,
            "expected_room_version": room.state_version,
        },
    )
    assert allowed.status_code == 200, allowed.content
    membership.refresh_from_db()
    assert membership.state == AdmissionState.NONE
    replay = post(keeper_client, f"{url}/{user.slug}/decline", body)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    membership.refresh_from_db()
    assert membership.state == AdmissionState.NONE
    assert client.get(f"{url}/me").json()["admitted_count"] == 0


@pytest.mark.django_db(transaction=True)
def test_returning_and_late_arrival_flags_are_snapshot_stable(context, livekit):
    client, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    room.status = "active"
    room.save(update_fields=["status"])
    url = f"{BASE}/{session.slug}/admission"
    approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
    assert approved.status_code == 200, approved.content
    first = client.get(f"{url}/me").json()["me"]
    assert (first["returning"], first["session_started"], first["late_arrival"]) == (False, True, True)
    new_ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
    returned = post(client, f"{url}/request", new_ids)
    assert returned.status_code == 200, returned.content
    me = returned.json()["me"]
    assert (me["returning"], me["session_started"], me["late_arrival"]) == (True, True, False)
    assert client.get(f"{url}/me").json()["me"]["attempt_id"] == new_ids["attempt_id"]


@pytest.mark.django_db(transaction=True)
def test_banned_and_wrong_identity_decisions_do_not_admit(context, livekit):
    _, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    other = UserFactory()
    session.attendees.add(other)
    body = decision_body(room, ids, attempt)
    assert post(keeper_client, f"{url}/{other.slug}/approve", body).status_code == 409
    room.banned_participants = [user.slug]
    room.save(update_fields=["banned_participants"])
    assert post(keeper_client, f"{url}/{user.slug}/approve", body).status_code == 403
    assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.NONE


@pytest.mark.django_db(transaction=True)
def test_me_does_not_disclose_other_waiting_participant(context, livekit):
    client, _, keeper_client, _, session, _ = context
    request_attempt(context)
    other = UserFactory()
    session.attendees.add(other)
    other_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(other)}")
    other_ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
    url = f"{BASE}/{session.slug}/admission"
    assert post(other_client, f"{url}/request", other_ids).status_code == 200
    me = client.get(f"{url}/me")
    assert me.status_code == 200
    assert me.json()["pending_count"] == 2
    assert other.slug not in me.content.decode()
    assert other_ids["request_id"] not in me.content.decode()
    assert other_ids["attempt_id"] not in me.content.decode()
    assert len(keeper_client.get(url).json()["waiting"]) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("duplicate", [True, False])
def test_concurrent_http_decisions_are_serialized(context, livekit, duplicate):
    _, user, _, keeper, session, room = context
    ids, attempt = request_attempt(context)
    body = decision_body(room, ids, attempt)
    url = f"{BASE}/{session.slug}/admission/{user.slug}"
    token = generate_jwt_token(keeper)
    barrier = Barrier(2, timeout=10)

    def decide(action, payload):
        close_old_connections()
        try:
            client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")
            barrier.wait()
            response = post(client, f"{url}/{action}", payload)
            return response.status_code, response.json()
        finally:
            close_old_connections()

    second_action = "approve" if duplicate else "decline"
    second_body = body if duplicate else {**body, "command_id": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(decide, "approve", body), executor.submit(decide, second_action, second_body)]
        responses = [future.result(timeout=30) for future in futures]
    if duplicate:
        assert [status for status, _ in responses] == [200, 200]
        assert sorted(data["replayed"] for _, data in responses) == [False, True]
    else:
        assert sorted(status for status, _ in responses) == [200, 409]
    assert AdmissionCommand.objects.filter(session=session).count() == 1
    attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
    assert attempt.status in ("granting", "declined")


@pytest.mark.django_db(transaction=True)
def test_out_of_order_connection_receipt_cannot_overwrite_newer_sid(context, livekit):
    from totem.rooms.admission.http import confirm_connection

    client, user, _, _, session, _ = context
    ids, _ = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission/request"
    calls = 0

    def observe(room_name, identity):
        nonlocal calls
        assert not connection.in_atomic_block
        calls += 1
        if calls == 1:
            confirm_connection(session.slug, user, UUID(ids["request_id"]), UUID(ids["attempt_id"]))
            return api.ParticipantInfo(identity=identity, sid="old-sid")
        return api.ParticipantInfo(identity=identity, sid="new-sid")

    with patch("totem.rooms.admission.http.get_participant_snapshot", side_effect=observe):
        response = post(client, url, {**ids, "connected": True})
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "stale_version"
    attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
    assert attempt.participant_sid == "new-sid"
    assert attempt.connected_at is not None


@pytest.mark.django_db(transaction=True)
def test_connection_receipt_accepts_approval_during_presence_lookup(context, livekit):
    client, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"

    def observe(room_name, identity):
        response = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
        assert response.status_code == 200, response.content
        return api.ParticipantInfo(identity=identity, sid=f"sid-{identity}")

    with patch("totem.rooms.admission.http.get_participant_snapshot", side_effect=observe):
        response = post(client, f"{url}/request", {**ids, "connected": True})
    assert response.status_code == 200, response.content
    assert response.json()["me"]["connected_at"] is not None
    assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.ADMITTED


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("action", ["admit-all", "settings"])
def test_batch_grants_once_per_participant(context, livekit, action):
    from totem.rooms.admission import permissions as admission_permissions

    _, user, keeper_client, _, session, room = context
    request_attempt(context)
    other = UserFactory()
    session.attendees.add(other)
    other_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(other)}")
    url = f"{BASE}/{session.slug}/admission"
    assert (
        post(other_client, f"{url}/request", {"request_id": str(uuid4()), "attempt_id": str(uuid4())}).status_code
        == 200
    )
    updates = admission_permissions.update_participant_permissions
    assert isinstance(updates, MagicMock)
    updates.reset_mock()
    room.refresh_from_db()
    body = {"command_id": str(uuid4()), "expected_room_version": room.state_version}
    if action == "settings":
        response = send(
            keeper_client,
            "patch",
            f"{url}/settings",
            {**body, "approval_required": False, "expected_revision": room.admission_revision},
        )
    else:
        response = post(keeper_client, f"{url}/admit-all", body)
    assert response.status_code == 200, response.content
    assert response.json()["partial_failure"] is False
    assert updates.call_count == 2
    assert {call.args[1] for call in updates.call_args_list} == {user.slug, other.slug}
    assert all(call.kwargs["admitted"] for call in updates.call_args_list)


@pytest.mark.django_db(transaction=True)
def test_batch_in_progress_lease_is_partial_failure(context, livekit):
    _, user, keeper_client, _, session, room = context
    request_attempt(context)
    sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
    sync.operation_id = uuid4()
    sync.lease_until = timezone.now() + timedelta(minutes=1)
    sync.save(update_fields=["operation_id", "lease_until"])
    room.refresh_from_db()
    response = post(
        keeper_client,
        f"{BASE}/{session.slug}/admission/admit-all",
        {"command_id": str(uuid4()), "expected_room_version": room.state_version},
    )
    assert response.status_code == 200, response.content
    assert response.json()["partial_failure"] is True
    result = response.json()["results"][0]
    assert result["identity"] == user.slug
    assert result["participant"]["permission_status"] == "in_progress"
    assert result["participant"]["last_error"] is None
    sync.refresh_from_db()
    assert sync.operation_id is not None
    assert sync.applied_revision != sync.revision


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("foreign", [False, True])
def test_connected_request_rejects_unknown_or_cross_session_ids(context, livekit, foreign):
    client, user, _, keeper, session, _ = context
    attempt = None
    if foreign:
        other = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
        other.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(other)
        attempt = admission.request_admission(other.slug, user, uuid4(), uuid4())
        ids = {"request_id": str(attempt.request_id), "attempt_id": str(attempt.attempt_id)}
    else:
        ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
    response = post(client, f"{BASE}/{session.slug}/admission/request", {**ids, "connected": True})
    assert response.status_code == 409
    assert response.json()["code"] == "invalid_attempt"
    assert not SessionAdmission.objects.filter(session=session, user=user).exists()
    if foreign:
        assert attempt is not None
        attempt.refresh_from_db()
        assert attempt.connected_at is None


@pytest.mark.django_db(transaction=True)
def test_ended_snapshot_reads_do_not_reschedule_intents_or_notify(context, livekit, admission_notification_transport):
    client, user, keeper_client, _, session, room = context
    request_attempt(context)
    room.status = "ended"
    room.save(update_fields=["status"])
    url = f"{BASE}/{session.slug}/admission"
    first = keeper_client.get(url)
    assert first.status_code == 200, first.content
    sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
    state = (sync.revision, sync.desired_admitted, sync.applied_revision, sync.retry_count, sync.next_retry_at)
    admission_notification_transport.reset_mock()
    for response in (client.get(f"{url}/me"), keeper_client.get(url), keeper_client.get(url)):
        assert response.status_code == 200, response.content
        assert response.json()["version"] == first.json()["version"]
    sync.refresh_from_db()
    assert (sync.revision, sync.desired_admitted, sync.applied_revision, sync.retry_count, sync.next_retry_at) == state
    admission_notification_transport.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_activation_receipts(context, livekit):
    client, user, keeper_client, _, session, room = context
    ids, _ = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    livekit.return_value = {user.slug}
    connected = post(client, f"{url}/request", {**ids, "connected": True})
    assert connected.status_code == 200, connected.content
    approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, connected.json()["me"]))
    assert approved.status_code == 200, approved.content
    current = client.get(f"{url}/me").json()["me"]
    receipt = {**ids, "expected_version": current["attempt_version"]}
    barrier = Barrier(2, timeout=10)
    token = generate_jwt_token(user)

    def activate():
        close_old_connections()
        try:
            thread_client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")
            barrier.wait()
            response = post(thread_client, f"{url}/activated", receipt)
            return response.status_code, response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(activate) for _ in range(2)]
        responses = [future.result(timeout=30) for future in futures]
    assert [status for status, _ in responses] == [200, 200], responses
    assert all(data["me"]["status"] == "activated" and data["activated_count"] == 1 for _, data in responses)
    assert session.joined.filter(pk=user.pk).count() == 1


@pytest.mark.django_db(transaction=True)
def test_activated_replacement_uses_a_fresh_attempt_without_reconnecting(context, livekit):
    client, user, keeper_client, _, session, room = context
    url = f"{BASE}/{session.slug}/admission"
    ids, _ = request_attempt(context)
    livekit.return_value = {user.slug}
    connected = post(client, f"{url}/request", {**ids, "connected": True})
    approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, connected.json()["me"]))
    assert approved.status_code == 200
    current = client.get(f"{url}/me").json()["me"]
    assert post(client, f"{url}/activated", {**ids, "expected_version": current["attempt_version"]}).status_code == 200

    def replacement(room_name, identity, **kwargs):
        assert not connection.in_atomic_block
        return api.ParticipantInfo(
            identity=identity,
            sid="new-activated-sid",
            permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
        )

    with (
        patch("totem.rooms.admission.http.get_participant_snapshot", side_effect=replacement),
        patch("totem.rooms.admission.permissions.get_participant_snapshot", side_effect=replacement),
        patch("totem.rooms.admission.permissions.update_participant_permissions", side_effect=replacement),
    ):
        assert post(client, f"{url}/request", {**ids, "connected": True}).status_code == 409
        fresh_ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
        assert post(client, f"{url}/request", fresh_ids).status_code == 200
        receipt = post(client, f"{url}/request", {**fresh_ids, "connected": True})
        assert receipt.status_code == 200, receipt.content
        assert receipt.json()["me"]["returning"] is True
        activated = post(
            client, f"{url}/activated", {**fresh_ids, "expected_version": receipt.json()["me"]["attempt_version"]}
        )
        assert activated.status_code == 200, activated.content
        assert activated.json()["me"]["status"] == "activated"


@pytest.mark.django_db(transaction=True)
def test_failed_notification_does_not_block_http_recovery(context, livekit, admission_notification_transport):
    client, user, keeper_client, _, session, room = context
    admission_notification_transport.side_effect = RuntimeError("missed notification")
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
    assert approved.status_code == 200, approved.content
    recovered = client.get(f"{url}/me")
    assert recovered.status_code == 200
    assert recovered.json()["me"]["admission_state"] == "admitted"
    assert recovered.json()["me"]["permission_status"] == "applied"
    assert recovered.json()["me"]["status"] == "approved"


@pytest.mark.django_db(transaction=True)
def test_refresh_hints_run_after_commit_and_use_current_keeper(context, livekit, admission_notification_transport):
    from django.db import transaction

    _, user, _, old_keeper, session, room = context
    replacement = UserFactory()
    session.attendees.add(replacement)

    def publish(room_name, version, destinations):
        assert not connection.in_atomic_block
        assert room_name == session.slug
        assert replacement.slug in destinations
        assert old_keeper.slug not in destinations
        assert version > 0
        return True

    admission_notification_transport.side_effect = publish
    with transaction.atomic():
        admission.request_admission(session.slug, user, uuid4(), uuid4())
        admission_notification_transport.assert_not_called()
        Room.objects.filter(pk=room.pk).update(keeper=replacement.slug)
    assert admission_notification_transport.call_count > 0


@pytest.mark.django_db(transaction=True)
def test_openapi_exposes_admission_schemas_without_service_import():
    from totem.api.api import mobile_api

    schema = mobile_api.get_openapi_schema()
    paths = schema["paths"]
    path = next(path for path in paths if path.endswith("/{session_slug}/admission/request"))
    operation = paths[path]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]
    assert {"200", "403", "404", "409", "503", "504"} <= {str(key) for key in operation["responses"]}
    assert "AdmissionMeSnapshot" in schema["components"]["schemas"]


@pytest.fixture
def setup_room(db):
    keeper = UserFactory()
    user = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    return session, room, keeper, user


def request(session, user):
    return admission.request_admission(session.slug, user, uuid4(), uuid4())


def decide(room, keeper, attempt, decision="approve"):
    room.refresh_from_db()
    return admission.decide_admission(
        room.session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        decision,
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )


def require_admission(session_slug, user) -> SessionAdmission:
    durable = admission.get_admission(session_slug, user)
    assert durable is not None
    return durable


def revoke(room, keeper, user):
    durable = require_admission(room.session.slug, user)
    room.refresh_from_db()
    return admission.revoke_admission(
        room.session.slug,
        keeper,
        user,
        expected_version=durable.version,
        expected_room_version=room.state_version,
    )


@pytest.mark.django_db
def test_keeper_cannot_record_join_without_admission(setup_room):
    session, room, keeper, _ = setup_room
    original_order = room.talking_order.copy()
    with pytest.raises(TransitionError) as error:
        record_join(session, keeper)
    assert error.value.code == ErrorCode.NOT_JOINABLE
    room.refresh_from_db()
    assert not session.joined.filter(pk=keeper.pk).exists()
    assert room.talking_order == original_order


@pytest.mark.django_db
def test_record_join_requires_admission_without_mutating_join_or_order(setup_room):
    session, room, _, user = setup_room
    original_order = room.talking_order.copy()
    with pytest.raises(TransitionError) as error:
        record_join(session, user)
    assert error.value.code == ErrorCode.NOT_JOINABLE
    room.refresh_from_db()
    assert not session.joined.filter(pk=user.pk).exists()
    assert room.talking_order == original_order


@pytest.mark.django_db
def test_record_join_admitted_succeeds_but_revoked_cannot_rejoin(setup_room):
    session, room, keeper, user = setup_room
    attempt = decide(room, keeper, request(session, user))
    with pytest.raises(TransitionError) as error:
        record_join(session, user)
    assert error.value.code == ErrorCode.NOT_JOINABLE
    assert not session.joined.filter(pk=user.pk).exists()

    attempt.status = AttemptStatus.ADMITTED
    attempt.participant_sid = "participant-1"
    attempt.connected_at = timezone.now()
    attempt.save(update_fields=["status", "participant_sid", "connected_at"])
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    sync.applied_revision = sync.revision
    sync.participant_sid = attempt.participant_sid
    sync.save(update_fields=["applied_revision", "participant_sid"])
    record_join(session, user)
    room.refresh_from_db()
    assert session.joined.filter(pk=user.pk).exists()
    assert user.slug in room.talking_order
    revoke(room, keeper, user)
    room.refresh_from_db()
    assert user.slug not in room.talking_order
    original_order = room.talking_order.copy()
    with pytest.raises(TransitionError) as error:
        record_join(session, user)
    assert error.value.code == ErrorCode.NOT_JOINABLE
    room.refresh_from_db()
    assert room.talking_order == original_order


@pytest.mark.django_db
def test_remove_revokes_before_livekit_failure(client_with_user):
    client, keeper = client_with_user
    user = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    decide(room, keeper, request(session, user))

    def fail_livekit(*args, **kwargs):
        assert require_admission(session.slug, user).state == "revoked"
        raise LiveKitConfigurationError("unavailable")

    with patch("totem.rooms.api.remove_participant", side_effect=fail_livekit) as remove:
        response = client.post(f"/api/mobile/protected/rooms/{session.slug}/remove/{user.slug}")
    assert response.status_code == 500
    remove.assert_called_once()
    assert require_admission(session.slug, user).state == "revoked"
    assert not admission.is_authorized_to_enter(session.slug, user)


@pytest.mark.django_db
def test_ban_revokes_admission_and_unban_does_not_restore(setup_room):
    session, room, keeper, user = setup_room
    attempt = decide(room, keeper, request(session, user))
    room.refresh_from_db()
    state = apply_event(
        session.slug,
        keeper.slug,
        BanParticipantEvent(participantSlug=user.slug),
        room.state_version,
        {keeper.slug, user.slug},
    )
    attempt.refresh_from_db()
    assert attempt.status == "revoked"
    assert require_admission(session.slug, user).state == "revoked"
    assert not admission.is_authorized_to_enter(session.slug, user)
    apply_event(
        session.slug, keeper.slug, UnbanParticipantEvent(participantSlug=user.slug), state.version, {keeper.slug}
    )
    room.refresh_from_db()
    assert user.slug not in room.banned_participants
    assert require_admission(session.slug, user).state == "revoked"
    assert not admission.is_authorized_to_enter(session.slug, user)


@pytest.mark.django_db
def test_background_end_invalidates_attempts_even_when_room_event_fails(setup_room):
    session, room, keeper, user = setup_room
    other = UserFactory()
    session.attendees.add(other)
    pending = request(session, user)
    granting = decide(room, keeper, request(session, other))
    with patch("totem.rooms.tasks.apply_event", side_effect=RuntimeError("event failed")) as event:
        _end_session(session, set())
    event.assert_called_once()
    session.refresh_from_db()
    pending.refresh_from_db()
    granting.refresh_from_db()
    assert session.ended_at is not None
    assert pending.status not in {"pending", "granting"}
    assert granting.status not in {"pending", "granting"}


@pytest.mark.django_db
@pytest.mark.parametrize("current_keeper_connected", [False, True])
def test_watchdog_uses_room_keeper_not_space_author(setup_room, current_keeper_connected):
    session, room, author, _ = setup_room
    session.start = timezone.now() - timedelta(minutes=10)
    session.save(update_fields=["start"])
    current_keeper = UserFactory()
    room.keeper = current_keeper.slug
    room.save(update_fields=["keeper"])
    connected = {current_keeper.slug} if current_keeper_connected else {author.slug}
    with (
        patch("totem.rooms.tasks.get_admission_participants", return_value=connected),
        patch("totem.rooms.tasks.publish_state"),
    ):
        count = end_sessions_without_keeper()
    session.refresh_from_db()
    assert count == (0 if current_keeper_connected else 1)
    assert (session.ended_at is None) == current_keeper_connected


@pytest.mark.django_db
def test_permanent_decline_survives_temporary_keeper_role(setup_room):
    session, room, keeper, user = setup_room
    decide(room, keeper, request(session, user), "permanently_decline")
    assert require_admission(session.slug, user).state == "permanently_declined"
    room.keeper = user.slug
    room.save(update_fields=["keeper"])
    attempt = request(session, user)
    assert attempt.status == "granting"
    assert require_admission(session.slug, user).state == "permanently_declined"
    room.keeper = keeper.slug
    room.save(update_fields=["keeper"])
    assert not admission.is_authorized_to_enter(session.slug, user)
    with pytest.raises(admission.AdmissionError) as error:
        request(session, user)
    assert error.value.code == "not_eligible"
    assert require_admission(session.slug, user).state == "permanently_declined"


@pytest.mark.django_db
def test_expired_decision_persists_expiration_immediately(setup_room):
    session, room, keeper, user = setup_room
    attempt = request(session, user)
    attempt.expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=["expires_at"])
    with pytest.raises(admission.AdmissionError):
        decide(room, keeper, attempt)
    attempt.refresh_from_db()
    assert attempt.status == "expired"
    assert require_admission(session.slug, user).state == "none"


@pytest.mark.django_db
def test_completion_rejects_other_user_and_mismatched_ids(setup_room):
    session, room, keeper, user = setup_room
    attempt = decide(room, keeper, request(session, user))
    other = UserFactory()
    session.attendees.add(other)
    for actor, request_id, attempt_id in [
        (other, attempt.request_id, attempt.attempt_id),
        (user, uuid4(), attempt.attempt_id),
        (user, attempt.request_id, uuid4()),
    ]:
        with pytest.raises(admission.AdmissionError) as error:
            admission.complete_admission(session.slug, actor, request_id, attempt_id, expected_version=attempt.version)
        assert error.value.code == "invalid_attempt"
    attempt.refresh_from_db()
    assert attempt.status == "granting"


@pytest.mark.django_db
@pytest.mark.parametrize("permanently_declined", [False, True])
def test_keeper_bypass_cannot_complete_after_reassignment(setup_room, permanently_declined):
    session, room, keeper, user = setup_room
    if permanently_declined:
        decide(room, keeper, request(session, user), "permanently_decline")
    room.keeper = user.slug
    room.save(update_fields=["keeper"])
    attempt = request(session, user)
    assert attempt.status == "granting"
    room.keeper = keeper.slug
    room.save(update_fields=["keeper"])
    with (
        patch(
            "totem.rooms.admission.permissions.verify_current_permissions", return_value=(1, "participant-1")
        ) as verify,
        pytest.raises(admission.AdmissionError) as error,
    ):
        admission.complete_admission(
            session.slug, user, attempt.request_id, attempt.attempt_id, expected_version=attempt.version
        )
    verify.assert_called_once_with(attempt.admission.pk)
    assert error.value.code == "not_eligible"
    attempt.refresh_from_db()
    assert attempt.status == "granting"
    assert not admission.is_authorized_to_enter(session.slug, user)


KEY = "test-key-test-key-test-key-test-key-test-key"
SECRET = "test-secret-test-secret-test-secret-test-secret-test-secret"


@pytest.fixture
def join_context(client_with_user, settings):
    settings.LIVEKIT_API_KEY = KEY
    settings.LIVEKIT_API_SECRET = SECRET
    client, user = client_with_user
    keeper = UserFactory()
    session = SessionFactory(
        space__author=keeper,
        space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
        start=timezone.now() - timedelta(minutes=5),
        duration_minutes=60,
    )
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    with patch("totem.rooms.api.get_admission_participants", return_value=set()) as presence:
        yield client, user, keeper, session, room, presence


def join(client, session, body=None):
    url = f"{BASE}/{session.slug}/join"
    if body is None:
        return client.post(url)
    return client.post(url, data=body, content_type="application/json")


def ids():
    return {"request_id": str(uuid4()), "attempt_id": str(uuid4())}


def assert_token(response, user, session, *, admitted, attempt_id=None):
    assert response.status_code == 200, response.content
    claims = jwt.decode(response.json()["token"], SECRET, algorithms=["HS256"])
    assert claims["sub"] == user.slug
    assert claims["name"] == (user.name or "Anonymous")
    assert claims["exp"] - claims["nbf"] == 60
    assert claims["video"] == {
        "room": session.slug,
        "roomJoin": True,
        "roomAdmin": False,
        "canPublish": admitted,
        "canSubscribe": admitted,
        "canPublishData": admitted,
        "canUpdateOwnMetadata": False,
        "hidden": False,
    }
    if attempt_id is not None:
        assert claims["attributes"] == {
            "totem.admission": "admitted" if admitted else "waiting",
            "totem.admission_attempt": attempt_id,
        }
    return claims


def assert_admission(response, session, user, *, status, permissions):
    assert response.status_code == 200, response.content
    data = response.json()["admission"]
    attempt = AdmissionAttempt.objects.get(attempt_id=UUID(data["attempt_id"]))
    assert str(attempt.request_id) == data["request_id"]
    assert attempt.admission.session_id == session.pk
    assert attempt.admission.user_id == user.pk
    assert data["status"] == status == attempt.status
    assert data["durable_state"] == attempt.admission.state
    assert abs(parse_datetime(data["expires_at"]) - attempt.expires_at) < timedelta(milliseconds=1)
    assert data["permissions"] == permissions
    sync = getattr(attempt.admission, "permission_sync", None)
    assert data["revision"] == (sync.revision if sync else 0)
    expected_sync = "pending"
    if sync:
        expected_sync = sync.last_error or ("applied" if sync.applied_revision == sync.revision else "pending")
    assert data["permission_sync"] == expected_sync
    return data


@pytest.mark.django_db
def test_waiting_join_returns_restricted_token_without_recording_join(join_context):
    client, user, _, session, _, presence = join_context
    requested = ids()
    response = join(client, session, requested)
    data = assert_admission(response, session, user, status="pending", permissions="waiting")
    assert {key: data[key] for key in requested} == requested
    assert data["approval_required"] is True
    assert data["durable_state"] == "none"
    assert_token(response, user, session, admitted=False, attempt_id=data["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()
    presence.assert_called_once_with(session.slug)


@pytest.mark.django_db
def test_keeper_join_bypasses_approval_without_recording_join(join_context):
    client, user, _, session, _, _ = join_context
    session.space.author = user
    session.space.save(update_fields=["author"])
    Room.objects.filter(session=session).update(keeper=user.slug)
    response = join(client, session)
    data = assert_admission(response, session, user, status="granting", permissions="admitted")
    assert_token(response, user, session, admitted=True, attempt_id=data["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_durable_admitted_member_can_return_after_newcomer_window(join_context):
    client, user, _, session, _, _ = join_context
    session.start = timezone.now() - timedelta(minutes=15)
    session.save(update_fields=["start"])
    SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
    assert not session.joined.filter(pk=user.pk).exists()
    response = join(client, session)
    data = assert_admission(response, session, user, status="granting", permissions="admitted")
    assert_token(response, user, session, admitted=True, attempt_id=data["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("state", [AdmissionState.NONE, AdmissionState.REVOKED])
def test_legacy_joined_does_not_extend_newcomer_window(join_context, state):
    client, user, _, session, _, _ = join_context
    session.start = timezone.now() - timedelta(minutes=15)
    session.save(update_fields=["start"])
    session.joined.add(user)
    SessionAdmission.objects.create(session=session, user=user, state=state)
    response = join(client, session)
    assert response.status_code == 403
    assert response.json()["detail"] == "not_eligible"
    assert "token" not in response.json()


@pytest.mark.django_db
def test_policy_toggle_promotes_pending_on_repeat(join_context):
    client, user, keeper, session, room, _ = join_context
    first = join(client, session)
    waiting = assert_admission(first, session, user, status="pending", permissions="waiting")
    assert_token(first, user, session, admitted=False, attempt_id=waiting["attempt_id"])
    room.refresh_from_db()
    admission.update_approval_required(
        session.slug, keeper, False, expected_revision=room.admission_revision, expected_room_version=room.state_version
    )
    second = join(client, session)
    granted = assert_admission(second, session, user, status="granting", permissions="admitted")
    assert (granted["request_id"], granted["attempt_id"]) == (waiting["request_id"], waiting["attempt_id"])
    assert granted["approval_required"] is False
    assert_token(second, user, session, admitted=True, attempt_id=granted["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_explicit_approval_with_failed_sync_issues_token_without_recording_attendance(join_context):
    client, user, keeper, session, room, _ = join_context
    waiting = assert_admission(join(client, session), session, user, status="pending", permissions="waiting")
    attempt = AdmissionAttempt.objects.get(attempt_id=waiting["attempt_id"])
    room.refresh_from_db()
    admission.decide_admission(
        session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        "approve",
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )
    sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
    sync.last_error = "unavailable"
    sync.save(update_fields=["last_error"])

    response = join(client, session)
    granted = assert_admission(response, session, user, status="granting", permissions="admitted")
    assert granted["attempt_id"] == waiting["attempt_id"]
    assert granted["permission_sync"] == "unavailable"
    assert_token(response, user, session, admitted=True, attempt_id=granted["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_revoked_previous_attendee_needs_fresh_waiting_attempt(join_context):
    client, user, keeper, session, room, _ = join_context
    initial = assert_admission(join(client, session), session, user, status="pending", permissions="waiting")
    attempt = AdmissionAttempt.objects.get(attempt_id=initial["attempt_id"])
    room.refresh_from_db()
    admission.decide_admission(
        session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        "approve",
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )
    session.joined.add(user)
    membership = SessionAdmission.objects.get(session=session, user=user)
    room.refresh_from_db()
    admission.revoke_admission(
        session.slug,
        keeper,
        user,
        expected_version=membership.version,
        expected_room_version=room.state_version,
    )
    rejected = join(client, session)
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "invalid_attempt"
    assert "token" not in rejected.json()

    fresh_ids = ids()
    response = join(client, session, fresh_ids)
    waiting = assert_admission(response, session, user, status="pending", permissions="waiting")
    assert waiting["attempt_id"] == fresh_ids["attempt_id"]
    assert waiting["durable_state"] == "revoked"
    assert_token(response, user, session, admitted=False, attempt_id=waiting["attempt_id"])
    assert session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body", ["{", "{}", '{"request_id":"not-a-uuid"}', '{"request_id":"00000000-0000-0000-0000-000000000001"}']
)
def test_invalid_json_join_body_is_rejected(join_context, body):
    client, user, _, session, _, presence = join_context
    response = client.post(f"{BASE}/{session.slug}/join", data=body, content_type="application/json")
    assert response.status_code == 400
    assert "token" not in response.json()
    assert not SessionAdmission.objects.filter(session=session, user=user).exists()
    presence.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("content_type", ["application/json", "application/x-www-form-urlencoded"])
def test_empty_body_reuses_pending_attempt(join_context, content_type):
    client, user, _, session, _, _ = join_context
    first = assert_admission(join(client, session), session, user, status="pending", permissions="waiting")
    response = client.post(f"{BASE}/{session.slug}/join", data="", content_type=content_type)
    retry = assert_admission(response, session, user, status="pending", permissions="waiting")
    assert (retry["request_id"], retry["attempt_id"]) == (first["request_id"], first["attempt_id"])
    assert_token(response, user, session, admitted=False, attempt_id=retry["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_permanent_decline_denied_even_when_approval_disabled(join_context):
    client, user, _, session, room, _ = join_context
    room.approval_required = False
    room.save(update_fields=["approval_required"])
    SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.PERMANENTLY_DECLINED)
    for body in (None, ids()):
        response = join(client, session, body)
        assert response.status_code == 403
        assert response.json()["detail"] == "permanently_declined"
        assert "token" not in response.json()
    assert not session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_pending_attempt_remains_valid_after_newcomer_window_until_expiry(join_context):
    client, user, _, session, _, _ = join_context
    first = join(client, session)
    waiting = assert_admission(first, session, user, status="pending", permissions="waiting")
    session.start = timezone.now() - timedelta(minutes=15)
    session.save(update_fields=["start"])
    repeat = join(client, session)
    again = assert_admission(repeat, session, user, status="pending", permissions="waiting")
    assert again["request_id"] == waiting["request_id"]
    assert again["attempt_id"] == waiting["attempt_id"]
    assert_token(repeat, user, session, admitted=False, attempt_id=again["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()
    AdmissionAttempt.objects.filter(attempt_id=again["attempt_id"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    expired = join(client, session)
    assert expired.status_code == 403
    assert expired.json()["detail"] == "invalid_attempt"
    assert "token" not in expired.json()
    fresh = join(client, session, ids())
    assert fresh.status_code == 403
    assert fresh.json()["detail"] == "not_eligible"


@pytest.mark.django_db
@pytest.mark.parametrize("terminal", [AttemptStatus.DECLINED, AttemptStatus.CANCELLED, AttemptStatus.EXPIRED])
def test_terminal_attempt_requires_explicit_new_ids(join_context, terminal):
    client, user, _, session, _, _ = join_context
    initial = ids()
    response = join(client, session, initial)
    assert_admission(response, session, user, status="pending", permissions="waiting")
    AdmissionAttempt.objects.filter(attempt_id=initial["attempt_id"]).update(status=terminal)
    for body in (None, initial):
        rejected = join(client, session, body)
        assert rejected.status_code == 403
        assert rejected.json()["detail"] == "invalid_attempt"
        assert "token" not in rejected.json()
    fresh_ids = ids()
    fresh = join(client, session, fresh_ids)
    data = assert_admission(fresh, session, user, status="pending", permissions="waiting")
    assert data["attempt_id"] == fresh_ids["attempt_id"]
    assert_token(fresh, user, session, admitted=False, attempt_id=data["attempt_id"])


@pytest.mark.django_db
def test_superseded_explicit_ids_never_return_normal_token(join_context):
    client, user, _, session, _, _ = join_context
    old_ids, new_ids = ids(), ids()
    assert join(client, session, old_ids).status_code == 200
    assert join(client, session, new_ids).status_code == 200
    SessionAdmission.objects.filter(session=session, user=user).update(state=AdmissionState.ADMITTED)
    rejected = join(client, session, old_ids)
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "invalid_attempt"
    assert "token" not in rejected.json()


@pytest.mark.django_db
def test_waiting_duplicate_presence_does_not_depend_on_joined(join_context):
    client, user, _, session, _, presence = join_context
    presence.return_value = {user.slug}
    response = join(client, session)
    data = assert_admission(response, session, user, status="pending", permissions="waiting")
    assert response.json()["is_already_present"] is True
    assert_token(response, user, session, admitted=False, attempt_id=data["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()
    presence.assert_called_once_with(session.slug)


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["unavailable", "timeout"])
def test_presence_failure_fails_closed(join_context, code):
    client, user, _, session, _, presence = join_context
    presence.side_effect = LiveKitPermissionError(code, "presence failed")
    response = join(client, session)
    assert response.status_code == 500
    assert response.json()["code"] == "livekit_error"
    assert response.json()["detail"] == code
    assert "token" not in response.json()
    assert not session.joined.filter(pk=user.pk).exists()
    assert not SessionAdmission.objects.filter(session=session, user=user).exists()


@pytest.mark.django_db
def test_missing_livekit_configuration_fails_closed(join_context, settings):
    client, user, _, session, _, _ = join_context
    settings.LIVEKIT_API_KEY = None
    response = join(client, session)
    assert response.status_code == 500
    assert response.json()["code"] == "livekit_error"
    assert response.json()["detail"] == "unavailable"
    assert "token" not in response.json()
    assert not session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("reason", ["ended", "banned", "cancelled", "not_attending", "too_early"])
def test_ineligible_join_is_denied(join_context, reason):
    client, user, _, session, room, _ = join_context
    if reason == "ended":
        room.status = RoomStatus.ENDED
        room.save(update_fields=["status"])
    elif reason == "banned":
        room.banned_participants = [user.slug]
        room.save(update_fields=["banned_participants"])
    elif reason == "cancelled":
        session.cancelled = True
        session.save(update_fields=["cancelled"])
    elif reason == "not_attending":
        session.attendees.remove(user)
    else:
        session.start = timezone.now() + timedelta(hours=2)
        session.save(update_fields=["start"])
    response = join(client, session)
    assert response.status_code == 403
    assert "token" not in response.json()
    assert not session.joined.filter(pk=user.pk).exists()


@override_settings(
    LIVEKIT_API_KEY="test-key-test-key-test-key-test-key",
    LIVEKIT_API_SECRET="test-secret-test-secret-test-secret-test-secret",
)
def test_token_room_capacity():
    token = room_livekit.create_access_token(User(slug="user", name="User"), "room")
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["roomConfig"]["maxParticipants"] == 15


def test_presence_is_raw_and_lookup_errors_are_not_empty():
    with patch("totem.rooms.livekit._get_connected_participants", new=AsyncMock(return_value={"waiting", "member"})):
        assert room_livekit.get_admission_participants("room") == {"waiting", "member"}
    with patch("totem.rooms.livekit._get_connected_participants", new=AsyncMock(side_effect=TimeoutError)):
        with pytest.raises(room_livekit.LiveKitPermissionError):
            room_livekit.get_admission_participants("room")


def test_first_join_proceeds_when_livekit_room_does_not_exist():
    user = User(is_active=True, pk=1, slug="keeper")
    session = MagicMock(slug="room")
    session.attendees.filter.return_value.exists.return_value = True
    session.end.return_value = room_api.timezone.now() + timedelta(hours=1)
    response = SimpleNamespace(is_already_present=True)
    missing = livekit_api.TwirpError(code="not_found", msg="room not found", status=404)
    with (
        patch.object(room_livekit, "_get_connected_participants", new=AsyncMock(side_effect=missing)),
        patch.object(room_api.Room.objects, "filter") as rooms,
        patch("totem.rooms.admission.prepare_admission_join", return_value=response) as prepare,
    ):
        rooms.return_value.first.return_value = SimpleNamespace(keeper="keeper")
        result = cast(Any, room_api._join_with_admission(session, user, None))
    assert result.status_code == 200
    assert prepare.call_args.kwargs["connected"] == set()
    assert not response.is_already_present


def test_admission_presence_internal_error_is_not_empty():
    error = livekit_api.TwirpError(code="internal", msg="unavailable", status=500)
    with patch.object(room_livekit, "_get_connected_participants", new=AsyncMock(side_effect=error)):
        with pytest.raises(room_livekit.LiveKitPermissionError, match="unavailable") as exc:
            room_livekit.get_admission_participants("room")
    assert exc.value.code == "unavailable"


def test_enforced_remove_is_hard_even_when_hint_succeeds():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.room.send_data = AsyncMock()
    client.room.remove_participant = AsyncMock()
    with patch("totem.rooms.livekit._get_api", return_value=client):
        room_livekit.remove_participant("room", "member", RemoveReason.REMOVE)
    client.room.remove_participant.assert_awaited_once()
    assert client.room.remove_participant.call_args.args[0].revoke_token_ts > 0


def test_reconcile_empty_presence_reaches_state_machine():
    request = cast(HttpRequest, SimpleNamespace(user=SimpleNamespace(slug="keeper")))
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
    request = cast(HttpRequest, SimpleNamespace(user=SimpleNamespace(slug="keeper")))
    body = EventRequest(event=StartRoomEvent(prompt=None), last_seen_version=0)
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
    request = cast(HttpRequest, SimpleNamespace(user=SimpleNamespace(slug="keeper")))
    body = EventRequest(event=StartRoomEvent(prompt=None), last_seen_version=0)
    with (
        patch.object(
            room_api, "get_room_participant_sids", side_effect=room_livekit.LiveKitPermissionError("timeout", "timeout")
        ),
        patch.object(room_api, "apply_event") as apply,
    ):
        result = cast(Any, room_api.post_event(request, "room", body))
    assert result.status_code == 500
    assert result.value.code == room_api.ErrorCode.LIVEKIT_ERROR
    apply.assert_not_called()


def test_waiting_participant_cannot_be_muted():
    request = cast(HttpRequest, SimpleNamespace(user=SimpleNamespace(slug="keeper")))
    with (
        patch.object(room_api, "_get_room_and_require_keeper", return_value=MagicMock()),
        patch.object(room_api, "get_room_participant_sids", return_value={"waiting": "sid-waiting"}),
        patch.object(room_api, "_project_connected", return_value=set()),
        patch.object(room_api, "mute_participant") as mute,
    ):
        result = cast(Any, room_api.mute(request, "room", "waiting"))
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
    with patch.object(room_livekit, "_get_api", return_value=client):
        assert room_livekit.get_room_participant_sids("room") == {"member": "sid-1"}
        client.room.list_participants.side_effect = livekit_api.TwirpError(
            code="not_found", msg="room not found", status=404
        )
        assert room_livekit.get_room_participant_sids("room") == {}
        client.room.list_participants.side_effect = TimeoutError()
        with pytest.raises(room_livekit.LiveKitPermissionError) as exc:
            room_livekit.get_room_participant_sids("room")
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
    request = cast(HttpRequest, SimpleNamespace(user=keeper))
    with (
        patch.object(room_api, "get_room_participant_sids", return_value={member.slug: "replacement-sid"}),
        patch.object(room_api, "mute_participant") as mute,
    ):
        result = cast(Any, room_api.mute(request, session.slug, member.slug))
    assert result.value.code == room_api.ErrorCode.NOT_IN_ROOM
    mute.assert_not_called()
    with (
        patch.object(room_api, "get_room_participant_sids", return_value={member.slug: attempt.participant_sid}),
        patch.object(room_api, "mute_participant") as mute,
    ):
        result = cast(Any, room_api.mute(request, session.slug, member.slug))
    assert result.status_code == 200
    mute.assert_called_once_with(session.slug, member.slug)


def test_join_passes_raw_presence_without_emitting_analytics():
    user = User(is_active=True, pk=1, slug="member")
    session = MagicMock(slug="room")
    session.attendees.filter.return_value.exists.return_value = True
    session.end.return_value = room_api.timezone.now() + timedelta(hours=1)
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
    request = cast(HttpRequest, SimpleNamespace(user=keeper))
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
