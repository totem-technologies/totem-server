from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone
from livekit import api

from totem.rooms import admission, tasks
from totem.rooms.admission import http as admission_http
from totem.rooms.admission import permissions as admission_permissions
from totem.rooms.livekit import LiveKitPermissionError
from totem.rooms.models import AdmissionPermissionSync, AdmissionState, AttemptStatus, Room
from totem.rooms.schemas import BanParticipantEvent, RoomStatus
from totem.rooms.state_machine import apply_event
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def context():
    keeper, user = UserFactory(), UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    with patch("totem.rooms.state_machine.publish_state"):
        yield session, room, keeper, user


@pytest.fixture
def queued_grant(context):
    session, room, keeper, user = context
    with patch.object(admission_permissions, "reconcile_admission_permissions"):
        attempt = admission.request_admission(session.slug, user, uuid4(), uuid4())
        room.refresh_from_db()
        attempt = admission.decide_admission(
            session.slug,
            keeper,
            attempt.request_id,
            attempt.attempt_id,
            "approve",
            expected_version=attempt.version,
            expected_room_version=room.state_version,
        )
    return attempt


def participant(identity):
    return api.ParticipantInfo(
        sid=f"sid-{identity}",
        identity=identity,
        permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
    )


def test_keeper_change_during_grant_fences_revision_and_compensates(context, queued_grant):
    session, room, _, user = context
    replacement = UserFactory()
    session.attendees.add(replacement)
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    original_revision = sync.revision
    calls = []

    def snapshot(room_name, identity):
        assert not connection.in_atomic_block
        return participant(identity)

    def update(room_name, identity, *, admitted, **kwargs):
        assert not connection.in_atomic_block
        calls.append(admitted)
        if admitted:
            Room.objects.filter(pk=room.pk).update(keeper=replacement.slug)
        return participant(identity)

    with (
        patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot),
        patch.object(admission_permissions, "update_participant_permissions", side_effect=update),
    ):
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
    sync.refresh_from_db()
    assert calls == [True, False]
    assert sync.revision > original_revision
    assert sync.authority_keeper == replacement.slug
    assert sync.applied_revision != sync.revision


@pytest.mark.parametrize("change", ["remove", "ban", "end"])
def test_grant_side_effect_after_removal_or_end_is_compensated(context, queued_grant, change):
    session, room, keeper, user = context
    calls = []
    if change == "ban":
        room.talking_order = [user.slug]
        room.save(update_fields=["talking_order"])

    def snapshot(room_name, identity):
        assert not connection.in_atomic_block
        return participant(identity)

    def update(room_name, identity, *, admitted, **kwargs):
        assert not connection.in_atomic_block
        calls.append(admitted)
        if admitted:
            if change == "ban":
                room.refresh_from_db()
                apply_event(
                    session.slug,
                    keeper.slug,
                    BanParticipantEvent(participant_slug=user.slug),
                    room.state_version,
                    connected=None,
                )
            elif change == "remove":
                room.refresh_from_db()
                admission.record_removal(session.slug, keeper, user, expected_room_version=room.state_version)
            else:
                session.ended_at = timezone.now()
                session.save(update_fields=["ended_at"])
        return participant(identity)

    with (
        patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot),
        patch.object(admission_permissions, "update_participant_permissions", side_effect=update),
        patch.object(admission_permissions, "hard_disconnect_participant"),
    ):
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id, force=True)
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    assert calls[0:2] == [True, False]
    assert all(not admitted for admitted in calls[1:])
    assert not sync.desired_admitted
    if change == "ban":
        room.refresh_from_db()
        queued_grant.admission.refresh_from_db()
        assert user.slug in room.banned_participants
        assert user.slug not in room.talking_order
        assert queued_grant.admission.state == AdmissionState.REVOKED


def test_complete_after_verified_grant_records_join_once(context, queued_grant):
    session, _, _, user = context

    def snapshot(room_name, identity):
        assert not connection.in_atomic_block
        return participant(identity)

    def update(room_name, identity, **kwargs):
        assert not connection.in_atomic_block
        return participant(identity)

    with (
        patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot),
        patch.object(admission_permissions, "update_participant_permissions", side_effect=update),
        patch("totem.users.analytics.event_joined") as joined,
    ):
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        result = admission.complete_admission(
            session.slug, user, queued_grant.request_id, queued_grant.attempt_id, expected_version=queued_grant.version
        )
        assert result.status == AttemptStatus.ADMITTED
        admission.complete_admission(
            session.slug, user, result.request_id, result.attempt_id, expected_version=result.version
        )
        assert session.joined.filter(pk=user.pk).exists()
        joined.assert_called_once()


@pytest.mark.parametrize("role", ["keeper", "attendee"])
def test_confirmed_activation_records_join_once(context, role):
    session, room, keeper, attendee = context
    user = keeper if role == "keeper" else attendee

    def snapshot(room_name, identity):
        assert not connection.in_atomic_block
        return participant(identity)

    def update(room_name, identity, **kwargs):
        assert not connection.in_atomic_block
        return participant(identity)

    with (
        patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot),
        patch.object(admission_permissions, "update_participant_permissions", side_effect=update),
        patch.object(admission_http, "get_participant_snapshot", side_effect=snapshot),
        patch("totem.users.analytics.event_joined") as joined,
    ):
        attempt = admission.request_admission(session.slug, user, uuid4(), uuid4())
        if role == "attendee":
            room.refresh_from_db()
            attempt = admission.decide_admission(
                session.slug,
                keeper,
                attempt.request_id,
                attempt.attempt_id,
                "approve",
                expected_version=attempt.version,
                expected_room_version=room.state_version,
            )
        assert not session.joined.filter(pk=user.pk).exists()
        assert joined.call_count == 0
        attempt = admission_http.confirm_connection(session.slug, user, attempt.request_id, attempt.attempt_id)
        attempt = admission.complete_admission(
            session.slug, user, attempt.request_id, attempt.attempt_id, expected_version=attempt.version
        )
        admission.complete_admission(
            session.slug, user, attempt.request_id, attempt.attempt_id, expected_version=attempt.version
        )
        assert session.joined.filter(pk=user.pk).exists()
        joined.assert_called_once()


def test_removal_before_activation_and_replayed_receipt_cannot_grant(context, queued_grant):
    session, room, keeper, user = context
    room.refresh_from_db()
    with patch.object(admission_permissions, "reconcile_admission_permissions"):
        admission.record_removal(session.slug, keeper, user, expected_room_version=room.state_version)
        replay = admission.request_admission(session.slug, user, queued_grant.request_id, queued_grant.attempt_id)
        assert replay.status == AttemptStatus.REVOKED
        with pytest.raises(admission.AdmissionError):
            admission.prepare_admission_join(
                session.slug, user, request_id=replay.request_id, attempt_id=replay.attempt_id, connected=set()
            )
    assert not session.joined.filter(pk=user.pk).exists()


def test_activated_attempt_cannot_grant_replacement_connection(context, queued_grant):
    session, _, _, user = context
    original = participant(user.slug)
    replacement = participant(user.slug)
    replacement.sid = "replacement-sid"
    with (
        patch.object(admission_permissions, "get_participant_snapshot", return_value=original),
        patch.object(admission_permissions, "update_participant_permissions", return_value=original),
        patch("totem.users.analytics.event_joined"),
    ):
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        activated = admission.complete_admission(
            session.slug,
            user,
            queued_grant.request_id,
            queued_grant.attempt_id,
            expected_version=queued_grant.version,
        )
    assert activated.status == AttemptStatus.ADMITTED
    with (
        patch.object(admission_permissions, "get_participant_snapshot", return_value=replacement),
        patch.object(admission_permissions, "update_participant_permissions", return_value=replacement) as update,
    ):
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id, force=True)
    assert [call.kwargs["admitted"] for call in update.call_args_list] == [False]
    sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
    assert sync.applied_revision is None
    assert sync.last_error == "identity_replaced"
    queued_grant.admission.refresh_from_db()
    assert queued_grant.admission.state == AdmissionState.ADMITTED
    with (
        patch.object(admission_permissions, "get_participant_snapshot", return_value=replacement),
        patch.object(admission_permissions, "update_participant_permissions", return_value=replacement),
        patch.object(admission_http, "get_participant_snapshot", return_value=replacement),
        patch("totem.users.analytics.event_joined"),
    ):
        fresh = admission.request_admission(session.slug, user, uuid4(), uuid4())
        fresh = admission_http.confirm_connection(session.slug, user, fresh.request_id, fresh.attempt_id)
        fresh = admission.complete_admission(
            session.slug,
            user,
            fresh.request_id,
            fresh.attempt_id,
            expected_version=fresh.version,
        )
    assert fresh.status == AttemptStatus.ADMITTED
    assert fresh.participant_sid == replacement.sid


def test_watchdog_retries_partial_room_end_without_presence(context):
    session, room, _, user = context
    with patch.object(admission_permissions, "reconcile_admission_permissions"):
        pending = admission.request_admission(session.slug, user, uuid4(), uuid4())
    session.start = timezone.now() - timedelta(minutes=10)
    session.save(update_fields=["start"])
    with (
        patch.object(tasks, "get_admission_participants", return_value=set()),
        patch.object(tasks, "apply_event", side_effect=RuntimeError("temporary cleanup failure")),
        patch.object(admission_permissions, "reconcile_admission_permissions"),
    ):
        assert tasks.end_sessions_without_keeper() == 1
    session.refresh_from_db()
    ended_at = session.ended_at
    assert ended_at is not None
    pending.refresh_from_db()
    assert pending.status == AttemptStatus.CANCELLED
    room.refresh_from_db()
    assert room.status != RoomStatus.ENDED
    with (
        patch.object(tasks, "get_admission_participants") as presence,
        patch.object(tasks, "publish_state") as publish,
        patch.object(admission_permissions, "reconcile_admission_permissions"),
    ):
        assert tasks.end_sessions_without_keeper() == 0
    presence.assert_not_called()
    publish.assert_called_once()
    room.refresh_from_db()
    session.refresh_from_db()
    assert room.status == RoomStatus.ENDED
    assert session.ended_at == ended_at


def test_watchdog_rechecks_keeper_changed_during_presence_lookup(context):
    session, room, _, user = context
    session.start = timezone.now() - timedelta(minutes=10)
    session.save(update_fields=["start"])

    def presence(slug):
        assert not connection.in_atomic_block
        Room.objects.filter(pk=room.pk).update(keeper=user.slug)
        return {user.slug}

    with patch.object(tasks, "get_admission_participants", side_effect=presence) as lookup:
        assert tasks.end_sessions_without_keeper() == 0
    lookup.assert_called_once_with(session.slug)
    session.refresh_from_db()
    assert session.ended_at is None


def test_watchdog_presence_failure_does_not_end_session(context):
    session, _, _, _ = context
    session.start = timezone.now() - timedelta(minutes=10)
    session.save(update_fields=["start"])
    with patch.object(tasks, "get_admission_participants", side_effect=LiveKitPermissionError("timeout", "offline")):
        assert tasks.end_sessions_without_keeper() == 0
    session.refresh_from_db()
    assert session.ended_at is None
