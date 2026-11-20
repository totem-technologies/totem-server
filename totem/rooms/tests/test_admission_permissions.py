from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import connection, transaction
from django.utils import timezone
from livekit import api

from totem.rooms import admission
from totem.rooms.admission import permissions as admission_permissions
from totem.rooms.livekit import LiveKitPermissionError
from totem.rooms.models import AdmissionPermissionSync, AdmissionState, Room
from totem.spaces.models import Session
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def livekit():
    participant = api.ParticipantInfo(
        sid="participant-1",
        identity="attendee",
        permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
    )

    def snapshot(*args, **kwargs):
        assert not connection.in_atomic_block
        return participant

    def update(*args, **kwargs):
        assert not connection.in_atomic_block
        return participant

    def disconnect(*args, **kwargs):
        assert not connection.in_atomic_block

    with (
        patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot) as get,
        patch.object(admission_permissions, "update_participant_permissions", side_effect=update) as update_mock,
        patch.object(admission_permissions, "hard_disconnect_participant", side_effect=disconnect) as hard_disconnect,
        patch("totem.rooms.livekit.get_participant_snapshot", side_effect=lambda *args, **kwargs: get(*args, **kwargs)),
        patch("totem.rooms.state_machine.publish_state"),
    ):
        yield get, update_mock, hard_disconnect


@pytest.fixture
def room_context(livekit):
    keeper = UserFactory()
    user = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    return session, room, keeper, user


def request(session, user):
    return admission.request_admission(session.slug, user, uuid4(), uuid4())


def approve(room, keeper, attempt):
    room.refresh_from_db()
    return admission.decide_admission(
        room.session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        "approve",
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )


def queue_without_callback(durable):
    with patch.object(admission_permissions, "reconcile_admission_permissions"):
        with transaction.atomic():
            Session.objects.select_for_update().get(pk=durable.session_id)
            admission_permissions.queue_permission_sync(durable)


@pytest.fixture
def queued_grant(room_context):
    session, room, keeper, user = room_context
    with patch.object(admission, "_queue_permissions"):
        attempt = approve(room, keeper, request(session, user))
    queue_without_callback(attempt.admission)
    return attempt


def test_approval_queues_and_grants_connected_participant(room_context, livekit):
    session, room, keeper, user = room_context
    attempt = approve(room, keeper, request(session, user))
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    assert attempt.status == "granting"
    assert sync.desired_admitted
    assert sync.applied_revision == sync.revision
    assert sync.participant_sid == "participant-1"
    assert sync.checked_at is not None
    assert sync.operation_id is None and sync.lease_until is None
    get, update, disconnect = livekit
    get.assert_called_with(session.slug, user.slug)
    update.assert_called_with(
        session.slug,
        user.slug,
        admitted=True,
        expected_sid="participant-1",
        attributes={"totem.admission": "admitted", "totem.admission_revision": str(sync.revision)},
    )
    disconnect.assert_not_called()
    snapshots_before_completion = get.call_count
    completed = admission.complete_admission(
        session.slug,
        user,
        attempt.request_id,
        attempt.attempt_id,
        expected_version=attempt.version,
    )
    assert completed.status == "admitted"
    assert get.call_count > snapshots_before_completion
    get.assert_called_with(session.slug, user.slug)


@pytest.mark.parametrize("code", ["participant_missing", "timeout", "identity_replaced"])
def test_failed_grant_stays_pending_until_retry(room_context, queued_grant, livekit, code):
    session, _, _, user = room_context
    attempt = queued_grant
    get, update, _ = livekit

    def fail(*args, **kwargs):
        assert not connection.in_atomic_block
        raise LiveKitPermissionError(code, "unavailable")

    get.side_effect = fail
    admission_permissions.reconcile_admission_permissions(attempt.admission_id)
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    assert sync.last_error == code
    assert sync.applied_revision is None
    assert sync.checked_at is not None
    attempt.refresh_from_db()
    assert attempt.status == "granting"
    with pytest.raises(admission.AdmissionError):
        admission.complete_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )

    def recovered(*args):
        assert not connection.in_atomic_block
        return api.ParticipantInfo(sid="participant-1", identity=user.slug)

    get.side_effect = recovered
    sync.next_retry_at = timezone.now() - timedelta(seconds=1)
    sync.save(update_fields=["next_retry_at"])
    assert admission_permissions.reconcile_session_permissions() >= 1
    sync.refresh_from_db()
    assert sync.last_error == ""
    assert sync.applied_revision == sync.revision
    assert update.call_args.kwargs["admitted"] is True


def test_stale_grant_is_restricted_and_not_acknowledged(room_context, queued_grant, livekit):
    session, _, _, user = room_context
    attempt = queued_grant
    _, update, _ = livekit

    def race(*args, **kwargs):
        assert not connection.in_atomic_block
        if kwargs["admitted"]:
            with transaction.atomic():
                Session.objects.select_for_update().get(pk=session.pk)
                durable = admission.get_admission(session.slug, user)
                durable.state = AdmissionState.REVOKED
                durable.save(update_fields=["state"])
                admission_permissions.queue_permission_sync(durable)
        return api.ParticipantInfo(sid="participant-1", identity=user.slug)

    update.side_effect = race
    admission_permissions.reconcile_admission_permissions(attempt.admission_id)
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    assert not sync.desired_admitted
    assert sync.applied_revision is None
    assert sync.last_error == "stale_operation"
    assert [call.kwargs["admitted"] for call in update.call_args_list] == [True, False]


def test_active_lease_skips_and_expired_lease_recovers(queued_grant, livekit):
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    sync.operation_id = uuid4()
    sync.lease_until = timezone.now() + timedelta(minutes=1)
    sync.save()
    admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
    livekit[0].assert_not_called()
    sync.refresh_from_db()
    assert sync.operation_id is not None
    sync.lease_until = timezone.now() - timedelta(seconds=1)
    sync.save(update_fields=["lease_until"])
    admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
    sync.refresh_from_db()
    assert sync.applied_revision is None
    assert sync.last_error == "lease_recovered"
    assert sync.operation_id is None and sync.lease_until is None
    assert livekit[1].call_count > 0
    assert all(call.kwargs["admitted"] is False for call in livekit[1].call_args_list)
    sync.next_retry_at = timezone.now() - timedelta(seconds=1)
    sync.save(update_fields=["next_retry_at"])
    admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
    sync.refresh_from_db()
    assert sync.applied_revision == sync.revision
    assert sync.last_error == ""


def test_periodic_rechecks_clean_row_for_replaced_identity(queued_grant, livekit):
    admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
    get, update, _ = livekit
    replacement = api.ParticipantInfo(sid="participant-2", identity="attendee")

    def snapshot(*args):
        assert not connection.in_atomic_block
        return replacement

    def apply(*args, **kwargs):
        assert not connection.in_atomic_block
        return replacement

    get.side_effect = snapshot
    update.side_effect = apply
    admission_permissions.reconcile_session_permissions()
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    assert sync.participant_sid == "participant-2"
    assert sync.applied_revision == sync.revision
    assert update.call_args.kwargs["expected_sid"] == "participant-2"


def test_revocation_applies_waiting_permissions(room_context, queued_grant, livekit):
    session, _, _, user = room_context
    durable = queued_grant.admission
    durable.state = AdmissionState.REVOKED
    durable.save(update_fields=["state"])
    queue_without_callback(durable)

    def disconnect_after_restrict(*args, **kwargs):
        assert not connection.in_atomic_block
        assert livekit[1].call_args.kwargs["admitted"] is False

    livekit[2].side_effect = disconnect_after_restrict
    admission_permissions.reconcile_admission_permissions(durable.pk)
    sync = AdmissionPermissionSync.objects.get(admission=durable)
    assert not sync.desired_admitted
    assert sync.applied_revision == sync.revision
    livekit[1].assert_called_with(
        session.slug,
        user.slug,
        admitted=False,
        expected_sid="participant-1",
        attributes={"totem.admission": "waiting", "totem.admission_revision": str(sync.revision)},
    )
    livekit[2].assert_called_once_with(session.slug, user.slug)


def test_revocation_failure_uses_hard_disconnect(room_context, queued_grant, livekit):
    session, _, _, user = room_context
    durable = queued_grant.admission
    durable.state = AdmissionState.REVOKED
    durable.save(update_fields=["state"])
    queue_without_callback(durable)
    _, update, disconnect = livekit

    def fail(*args, **kwargs):
        assert not connection.in_atomic_block
        raise LiveKitPermissionError("timeout", "unavailable")

    update.side_effect = fail
    admission_permissions.reconcile_admission_permissions(durable.pk)
    assert all(call.kwargs["admitted"] is False for call in update.call_args_list)
    disconnect.assert_called_once_with(session.slug, user.slug)
    sync = AdmissionPermissionSync.objects.get(admission=durable)
    assert not sync.desired_admitted
    assert sync.applied_revision is None
    assert sync.last_error == "timeout"


def test_dirty_old_ended_session_is_retried(room_context, queued_grant, livekit):
    session, _, _, _ = room_context
    session.ended_at = timezone.now() - timedelta(minutes=5)
    session.save(update_fields=["ended_at"])
    admission_permissions.reconcile_session_permissions()
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    assert not sync.desired_admitted
    assert sync.applied_revision == sync.revision
    assert livekit[1].call_args.kwargs["admitted"] is False
    livekit[2].assert_called_once()


@pytest.mark.parametrize("denied", [False, True])
def test_absent_participant_only_acknowledges_denial(queued_grant, livekit, denied):
    durable = queued_grant.admission
    if denied:
        durable.state = AdmissionState.REVOKED
        durable.save(update_fields=["state"])
        queue_without_callback(durable)

    def missing(*args, **kwargs):
        assert not connection.in_atomic_block
        raise LiveKitPermissionError("participant_missing", "Not connected")

    livekit[0].side_effect = missing
    admission_permissions.reconcile_admission_permissions(durable.pk)
    sync = AdmissionPermissionSync.objects.get(admission=durable)
    if denied:
        assert sync.applied_revision == sync.revision
        assert sync.last_error == ""
    else:
        assert sync.applied_revision is None
        assert sync.last_error == "participant_missing"


def test_clean_ended_row_is_rechecked_after_token_ttl_before_retirement(room_context, queued_grant, livekit):
    session, _, _, user = room_context
    ended_at = timezone.now() - timedelta(minutes=3)
    session.ended_at = ended_at
    session.save(update_fields=["ended_at"])
    get, update, disconnect = livekit

    def missing(*args, **kwargs):
        assert not connection.in_atomic_block
        raise LiveKitPermissionError("participant_missing", "Not connected")

    get.side_effect = missing
    admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    assert sync.applied_revision == sync.revision
    assert not sync.desired_admitted
    # The first absent observation occurred before the issued token's TTL elapsed.
    sync.checked_at = ended_at + timedelta(minutes=1)
    sync.save(update_fields=["checked_at"])

    def replayed(*args, **kwargs):
        assert not connection.in_atomic_block
        return api.ParticipantInfo(sid="replayed", identity=user.slug)

    get.side_effect = replayed
    update.side_effect = replayed
    assert admission_permissions.reconcile_session_permissions() == 1
    sync.refresh_from_db()
    assert sync.checked_at >= ended_at + timedelta(minutes=2)
    assert sync.applied_revision == sync.revision
    assert update.call_args.kwargs["admitted"] is False
    disconnect.assert_called_once_with(session.slug, user.slug)
    get.reset_mock()
    assert admission_permissions.reconcile_session_permissions() == 0
    get.assert_not_called()


def test_fresh_request_after_revocation_remains_waiting(room_context, queued_grant, livekit):
    session, room, keeper, user = room_context
    durable = queued_grant.admission
    room.refresh_from_db()
    admission.revoke_admission(
        session.slug,
        keeper,
        user,
        expected_version=durable.version,
        expected_room_version=room.state_version,
    )
    for mock in livekit:
        mock.reset_mock()
    attempt = request(session, user)
    durable.refresh_from_db()
    sync = AdmissionPermissionSync.objects.get(admission=durable)
    assert durable.state == AdmissionState.REVOKED
    assert attempt.status == "pending"
    assert not sync.desired_admitted
    assert sync.applied_revision == sync.revision
    assert livekit[1].call_args.kwargs["admitted"] is False
    livekit[2].assert_not_called()


def test_pending_waiting_participant_is_not_disconnected(room_context, livekit):
    session, _, _, user = room_context
    attempt = request(session, user)
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    assert not sync.desired_admitted
    assert livekit[1].call_args.kwargs["admitted"] is False
    livekit[2].assert_not_called()


def test_disabling_approval_grants_pending_without_new_token(room_context, livekit):
    session, room, keeper, user = room_context
    attempt = request(session, user)
    for mock in livekit:
        mock.reset_mock()
    room.refresh_from_db()
    with patch("totem.rooms.livekit.create_access_token") as token:
        admission.update_approval_required(
            session.slug,
            keeper,
            False,
            expected_revision=room.admission_revision,
            expected_room_version=room.state_version,
        )
    attempt.refresh_from_db()
    assert attempt.status == "granting"
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    assert sync.desired_admitted and sync.applied_revision == sync.revision
    assert any(call.kwargs["admitted"] is True for call in livekit[1].call_args_list)
    token.assert_not_called()


@pytest.mark.parametrize("stale", ["keeper", "attempt", "room"])
def test_stale_decision_never_grants(room_context, livekit, stale):
    session, room, keeper, user = room_context
    attempt = request(session, user)
    for mock in livekit:
        mock.reset_mock()
    room.refresh_from_db()
    if stale == "keeper":
        room.keeper = user.slug
        room.save(update_fields=["keeper"])
    with pytest.raises(admission.AdmissionError):
        admission.decide_admission(
            session.slug,
            keeper,
            attempt.request_id,
            attempt.attempt_id,
            "approve",
            expected_version=attempt.version + (stale == "attempt"),
            expected_room_version=room.state_version + (stale == "room"),
        )
    attempt.refresh_from_db()
    assert attempt.status == "pending"
    assert not any(call.kwargs["admitted"] for call in livekit[1].call_args_list)


def test_completion_reconciles_when_participant_connects_after_initial_miss(room_context, livekit):
    session, room, keeper, user = room_context
    get, update, _ = livekit

    def missing(*args, **kwargs):
        assert not connection.in_atomic_block
        raise LiveKitPermissionError("participant_missing", "Not connected")

    get.side_effect = missing
    attempt = approve(room, keeper, request(session, user))
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    assert sync.last_error == "participant_missing"
    assert sync.applied_revision is None
    update.reset_mock()
    participant = api.ParticipantInfo(
        sid="connected-after-approval",
        identity=user.slug,
        permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
    )

    def connected(*args, **kwargs):
        assert not connection.in_atomic_block
        return participant

    get.side_effect = connected
    get.reset_mock()
    update.side_effect = connected
    sync.next_retry_at = timezone.now() - timedelta(seconds=1)
    sync.save(update_fields=["next_retry_at"])
    completed = admission.complete_admission(
        session.slug,
        user,
        attempt.request_id,
        attempt.attempt_id,
        expected_version=attempt.version,
    )
    sync.refresh_from_db()
    assert completed.status == "admitted"
    assert sync.applied_revision == sync.revision
    assert sync.participant_sid == participant.sid
    assert update.call_args.kwargs["admitted"] is True
    assert get.call_count >= 2


@pytest.mark.parametrize("failure", ["replaced", "disconnected", "timeout", "revision_changed"])
def test_completion_rechecks_live_participant_and_journal(room_context, queued_grant, livekit, failure):
    session, _, _, user = room_context
    attempt = queued_grant
    admission_permissions.reconcile_admission_permissions(attempt.admission_id)
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    assert sync.applied_revision == sync.revision

    def snapshot(*args, **kwargs):
        assert not connection.in_atomic_block
        if failure in {"disconnected", "timeout"}:
            raise LiveKitPermissionError(
                "participant_missing" if failure == "disconnected" else "timeout", "unavailable"
            )
        if failure == "revision_changed":
            AdmissionPermissionSync.objects.filter(pk=sync.pk).update(revision=sync.revision + 1)
        return api.ParticipantInfo(
            sid="participant-2" if failure == "replaced" else "participant-1",
            identity=user.slug,
            permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
        )

    livekit[0].side_effect = snapshot
    with pytest.raises(admission.AdmissionError) as error:
        admission.complete_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )
    assert error.value.code == "permission_pending"
    attempt.refresh_from_db()
    assert attempt.status == "granting"
