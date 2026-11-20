from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from livekit import api

from totem.rooms import admission
from totem.rooms.admission import http as admission_http
from totem.rooms.admission import permissions as admission_permissions
from totem.rooms.admission.schemas import MembershipCommandInput
from totem.rooms.livekit import LiveKitPermissionError
from totem.rooms.models import AdmissionPermissionSync
from totem.rooms.tests.test_admission_permissions import livekit as livekit
from totem.rooms.tests.test_admission_permissions import queued_grant as queued_grant
from totem.rooms.tests.test_admission_permissions import room_context as room_context

pytestmark = pytest.mark.django_db(transaction=True)


def test_failures_back_off_and_periodic_scans_wait_until_due(queued_grant, livekit):
    get, update, disconnect = livekit
    get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
    for count, delay in enumerate([2, 4, 8, 16, 32, 60, 60], 1):
        before = timezone.now()
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        after = timezone.now()
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        assert sync.retry_count == count
        assert before + timedelta(seconds=delay) <= sync.next_retry_at <= after + timedelta(seconds=delay)
        calls = (get.call_count, update.call_count, disconnect.call_count)
        for _ in range(3):
            admission_permissions.reconcile_session_permissions()
        assert (get.call_count, update.call_count, disconnect.call_count) == calls
        sync.refresh_from_db()
        assert sync.retry_count == count
        sync.next_retry_at = timezone.now() - timedelta(seconds=1)
        sync.save(update_fields=["next_retry_at"])

    get.side_effect = None
    get.return_value = api.ParticipantInfo(sid="recovered")
    admission_permissions.reconcile_session_permissions()
    sync.refresh_from_db()
    assert sync.applied_revision == sync.revision
    assert sync.retry_count == 0 and sync.next_retry_at is None


def test_revoke_preempts_failed_grant_and_never_retries_it(room_context, queued_grant, livekit):
    session, room, keeper, user = room_context
    get, update, _ = livekit
    get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
    admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    old_revision = sync.revision
    assert sync.next_retry_at > timezone.now()
    get.side_effect = None
    get.return_value = api.ParticipantInfo(sid="participant-1", identity=user.slug)
    update.reset_mock()
    room.refresh_from_db()
    durable = queued_grant.admission
    admission.revoke_admission(
        session.slug, keeper, user, expected_version=durable.version, expected_room_version=room.state_version
    )
    sync.refresh_from_db()
    assert sync.revision > old_revision
    assert not sync.desired_admitted and sync.applied_revision == sync.revision
    assert sync.retry_count == 0 and sync.next_retry_at is None
    assert update.call_args.kwargs["admitted"] is False
    admission_permissions.reconcile_session_permissions()
    assert all(not call.kwargs["admitted"] for call in update.call_args_list)


def test_connection_sid_change_preempts_backoff_but_same_sid_does_not(room_context, queued_grant, livekit):
    session, _, _, user = room_context
    get, update, _ = livekit
    attempt = queued_grant
    participant = api.ParticipantInfo(sid="new-sid", identity=user.slug)
    get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
    admission_permissions.reconcile_admission_permissions(attempt.admission_id)
    sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
    old_revision = sync.revision
    get.side_effect = None
    get.return_value = participant
    update.return_value = participant
    with patch.object(admission_http, "get_participant_snapshot", return_value=participant):
        admission_http.confirm_connection(session.slug, user, attempt.request_id, attempt.attempt_id)
        sync.refresh_from_db()
        assert sync.revision > old_revision
        assert sync.applied_revision == sync.revision
        assert sync.retry_count == 0 and sync.next_retry_at is None
        assert update.call_args.kwargs["expected_sid"] == participant.sid
        get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
        admission_permissions.reconcile_admission_permissions(attempt.admission_id)
        sync.refresh_from_db()
        revision, due = sync.revision, sync.next_retry_at
        calls = (get.call_count, update.call_count)
        admission_http.confirm_connection(session.slug, user, attempt.request_id, attempt.attempt_id)
        sync.refresh_from_db()
        assert (sync.revision, sync.next_retry_at, sync.retry_count) == (revision, due, 1)
        assert (get.call_count, update.call_count) == calls


def test_removal_during_backoff_never_retries_grant(room_context, queued_grant, livekit):
    session, _, _, user = room_context
    get, update, _ = livekit
    get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
    admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    assert sync.desired_admitted and sync.next_retry_at > timezone.now()
    session.attendees.remove(user)
    get.side_effect = None
    get.return_value = api.ParticipantInfo(sid="participant-1", identity=user.slug)
    update.reset_mock()
    admission_permissions.reconcile_session_permissions()
    sync.refresh_from_db()
    assert not sync.desired_admitted
    assert sync.applied_revision == sync.revision
    assert update.call_args.kwargs["admitted"] is False
    assert all(not call.kwargs["admitted"] for call in update.call_args_list)


def test_command_response_reports_current_version_and_retry_status(room_context, queued_grant, livekit):
    session, room, keeper, user = room_context
    get, update, disconnect = livekit
    for mock in (get, update, disconnect):
        mock.side_effect = LiveKitPermissionError("timeout", "unavailable")
    room.refresh_from_db()
    body = MembershipCommandInput(
        command_id=uuid4(), expected_version=queued_grant.admission.version, expected_room_version=room.state_version
    )
    with patch.object(admission_http, "get_admission_participants", return_value=set()):
        response = admission_http.execute_keeper_command(session.slug, keeper, "revoke", body, user.slug)
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    room.refresh_from_db()
    assert response.snapshot.version == room.admission_version
    assert response.partial_failure
    participant = response.results[0].participant
    assert participant.permission_revision == sync.revision
    assert participant.last_error == "timeout"
    assert participant.next_retry_at == sync.next_retry_at
    assert sync.next_retry_at > timezone.now()


def test_ended_cleanup_reads_do_not_reset_denial_backoff(room_context, queued_grant, livekit):
    session, room, _, user = room_context
    session.ended_at = timezone.now()
    session.save(update_fields=["ended_at"])
    get, update, disconnect = livekit
    get.side_effect = LiveKitPermissionError("timeout", "unavailable")
    update.side_effect = LiveKitPermissionError("timeout", "unavailable")
    disconnect.side_effect = LiveKitPermissionError("timeout", "unavailable")
    admission.get_admission(session.slug, user)
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    assert not sync.desired_admitted and sync.retry_count > 0
    before = (sync.revision, sync.retry_count, sync.next_retry_at)
    room.refresh_from_db()
    version = room.admission_version
    calls = (get.call_count, update.call_count, disconnect.call_count)
    for _ in range(3):
        admission.get_admission(session.slug, user)
    sync.refresh_from_db()
    room.refresh_from_db()
    assert (sync.revision, sync.retry_count, sync.next_retry_at) == before
    assert room.admission_version == version
    assert (get.call_count, update.call_count, disconnect.call_count) == calls
