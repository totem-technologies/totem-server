import os
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import jwt
import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from totem.rooms import admission
from totem.rooms.livekit import LiveKitPermissionError
from totem.rooms.models import AdmissionAttempt, AdmissionState, AttemptStatus, Room, SessionAdmission
from totem.rooms.schemas import RoomStatus
from totem.spaces.models import Space
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db
KEY = "test-key-test-key-test-key-test-key-test-key"
SECRET = "test-secret-test-secret-test-secret-test-secret-test-secret"
BASE = "/api/mobile/protected/rooms"


@pytest.fixture
def join_context(client_with_user, settings):
    settings.SERVER_ENFORCED_ADMISSION = True
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


def test_keeper_join_bypasses_approval_without_recording_join(join_context):
    client, user, _, session, _, _ = join_context
    session.space.author = user
    session.space.save(update_fields=["author"])
    Room.objects.filter(session=session).update(keeper=user.slug)
    response = join(client, session)
    data = assert_admission(response, session, user, status="granting", permissions="admitted")
    assert_token(response, user, session, admitted=True, attempt_id=data["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()


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
    sync = SessionAdmission.objects.get(session=session, user=user).permission_sync
    sync.last_error = "unavailable"
    sync.save(update_fields=["last_error"])

    response = join(client, session)
    granted = assert_admission(response, session, user, status="granting", permissions="admitted")
    assert granted["attempt_id"] == waiting["attempt_id"]
    assert granted["permission_sync"] == "unavailable"
    assert_token(response, user, session, admitted=True, attempt_id=granted["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()


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


@pytest.mark.parametrize("content_type", ["application/json", "application/x-www-form-urlencoded"])
def test_empty_body_reuses_pending_attempt(join_context, content_type):
    client, user, _, session, _, _ = join_context
    first = assert_admission(join(client, session), session, user, status="pending", permissions="waiting")
    response = client.post(f"{BASE}/{session.slug}/join", data="", content_type=content_type)
    retry = assert_admission(response, session, user, status="pending", permissions="waiting")
    assert (retry["request_id"], retry["attempt_id"]) == (first["request_id"], first["attempt_id"])
    assert_token(response, user, session, admitted=False, attempt_id=retry["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()


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


def test_waiting_duplicate_presence_does_not_depend_on_joined(join_context):
    client, user, _, session, _, presence = join_context
    presence.return_value = {user.slug}
    response = join(client, session)
    data = assert_admission(response, session, user, status="pending", permissions="waiting")
    assert response.json()["is_already_present"] is True
    assert_token(response, user, session, admitted=False, attempt_id=data["attempt_id"])
    assert not session.joined.filter(pk=user.pk).exists()
    presence.assert_called_once_with(session.slug)


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


def test_missing_livekit_configuration_fails_closed(join_context, settings):
    client, user, _, session, _, _ = join_context
    settings.LIVEKIT_API_KEY = None
    response = join(client, session)
    assert response.status_code == 500
    assert response.json()["code"] == "livekit_error"
    assert response.json()["detail"] == "unavailable"
    assert "token" not in response.json()
    assert not session.joined.filter(pk=user.pk).exists()


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


def test_admission_flag_defaults_off(settings):
    if "SERVER_ENFORCED_ADMISSION" in os.environ:
        pytest.skip("Admission flag explicitly configured in environment")
    assert settings.SERVER_ENFORCED_ADMISSION is False


def test_legacy_join_response_has_no_admission(join_context, settings):
    client, user, _, session, _, presence = join_context
    settings.SERVER_ENFORCED_ADMISSION = False
    with patch("totem.rooms.api.get_connected_participants", return_value=set()):
        response = join(client, session)
    assert_token(response, user, session, admitted=True)
    assert response.json()["admission"] is None
    assert session.joined.filter(pk=user.pk).exists()
    presence.assert_not_called()
