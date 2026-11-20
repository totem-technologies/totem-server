from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection
from django.test import Client
from django.utils import timezone
from livekit import api

from totem.api.auth import generate_jwt_token
from totem.rooms import admission
from totem.rooms.livekit import LiveKitPermissionError
from totem.rooms.models import AdmissionAttempt, AdmissionCommand, AdmissionState, Room, SessionAdmission
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db(transaction=True)
BASE = "/api/mobile/protected/rooms"


@pytest.fixture
def context(settings, client_with_user):
    settings.SERVER_ENFORCED_ADMISSION = True
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


def test_request_then_me_returns_own_pending_attempt(settings, client_with_user, livekit):
    settings.SERVER_ENFORCED_ADMISSION = True
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


@pytest.mark.parametrize("method,suffix,body,keeper_only", endpoint_cases())
def test_disabled_and_unauthenticated_endpoints(context, settings, method, suffix, body, keeper_only):
    client, _, _, _, session, _ = context
    url = f"{BASE}/{session.slug}/admission{suffix}"
    settings.SERVER_ENFORCED_ADMISSION = False
    response = send(client, method, url, body)
    assert response.status_code == 404
    assert response.json()["code"] == "feature_disabled"
    settings.SERVER_ENFORCED_ADMISSION = True
    response = send(Client(), method, url, body)
    assert response.status_code == 401


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


def test_stale_attempt_version_rejects_rapid_second_decision(context, livekit):
    _, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission/{user.slug}"
    body = decision_body(room, ids, attempt)
    assert post(keeper_client, f"{url}/approve", body).status_code == 200
    response = post(keeper_client, f"{url}/decline", {**body, "command_id": str(uuid4())})
    assert response.status_code == 409
    assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.ADMITTED


def test_cancel_then_stale_approval_cannot_admit(context, livekit):
    client, user, keeper_client, _, session, room = context
    ids, attempt = request_attempt(context)
    url = f"{BASE}/{session.slug}/admission"
    decision = decision_body(room, ids, attempt)
    cancelled = post(client, f"{url}/cancel", {**ids, "expected_version": attempt["attempt_version"]})
    assert cancelled.status_code == 200, cancelled.content
    assert post(keeper_client, f"{url}/{user.slug}/approve", decision).status_code == 409
    assert SessionAdmission.objects.get(session=session, user=user).state != AdmissionState.ADMITTED


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
    sync = SessionAdmission.objects.get(session=session, user=user).permission_sync
    assert sync.applied_revision != sync.revision
    assert sync.retry_count > 0
    assert sync.next_retry_at is not None
    assert SessionAdmission.objects.get(session=session, user=other).state == AdmissionState.ADMITTED


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
            confirm_connection(session.slug, user, ids["request_id"], ids["attempt_id"])
            return api.ParticipantInfo(identity=identity, sid="old-sid")
        return api.ParticipantInfo(identity=identity, sid="new-sid")

    with patch("totem.rooms.admission.http.get_participant_snapshot", side_effect=observe):
        response = post(client, url, {**ids, "connected": True})
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "stale_version"
    attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
    assert attempt.participant_sid == "new-sid"
    assert attempt.connected_at is not None


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


def test_batch_in_progress_lease_is_partial_failure(context, livekit):
    _, user, keeper_client, _, session, room = context
    request_attempt(context)
    sync = SessionAdmission.objects.get(session=session, user=user).permission_sync
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


@pytest.mark.parametrize("foreign", [False, True])
def test_connected_request_rejects_unknown_or_cross_session_ids(context, livekit, foreign):
    client, user, _, keeper, session, _ = context
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
        attempt.refresh_from_db()
        assert attempt.connected_at is None


def test_ended_snapshot_reads_do_not_reschedule_intents_or_notify(context, livekit, admission_notification_transport):
    client, user, keeper_client, _, session, room = context
    request_attempt(context)
    room.status = "ended"
    room.save(update_fields=["status"])
    url = f"{BASE}/{session.slug}/admission"
    first = keeper_client.get(url)
    assert first.status_code == 200, first.content
    sync = SessionAdmission.objects.get(session=session, user=user).permission_sync
    state = (sync.revision, sync.desired_admitted, sync.applied_revision, sync.retry_count, sync.next_retry_at)
    admission_notification_transport.reset_mock()
    for response in (client.get(f"{url}/me"), keeper_client.get(url), keeper_client.get(url)):
        assert response.status_code == 200, response.content
        assert response.json()["version"] == first.json()["version"]
    sync.refresh_from_db()
    assert (sync.revision, sync.desired_admitted, sync.applied_revision, sync.retry_count, sync.next_retry_at) == state
    admission_notification_transport.assert_not_called()


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


def test_openapi_exposes_admission_schemas_without_service_import():
    from totem.api.api import mobile_api

    schema = mobile_api.get_openapi_schema()
    paths = schema["paths"]
    path = next(path for path in paths if path.endswith("/{session_slug}/admission/request"))
    operation = paths[path]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]
    assert {"200", "403", "404", "409", "503", "504"} <= {str(key) for key in operation["responses"]}
    assert "AdmissionMeSnapshot" in schema["components"]["schemas"]
