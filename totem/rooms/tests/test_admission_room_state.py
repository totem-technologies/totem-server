from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from totem.rooms.models import (
    AdmissionAttempt,
    AdmissionPermissionSync,
    AdmissionState,
    AttemptStatus,
    Room,
    SessionAdmission,
)
from totem.rooms.room_participants import participant_projection
from totem.rooms.schemas import (
    AcceptStickEvent,
    BanParticipantEvent,
    EmptyRoomEvent,
    EndReason,
    EndRoomEvent,
    ErrorCode,
    PassStickEvent,
    ReorderEvent,
    RoomStatus,
    StartRoomEvent,
    TransitionError,
    TurnState,
)
from totem.rooms.state_machine import apply_event, record_join
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def room_context(settings):
    settings.SERVER_ENFORCED_ADMISSION = True
    keeper, member, pending = UserFactory(), UserFactory(), UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, member, pending)
    room = Room.objects.get_or_create_for_session(session)
    return session, room, keeper, member, pending


def activate(session, user, state=AdmissionState.ADMITTED):
    admission = SessionAdmission.objects.create(session=session, user=user, state=state)
    attempt = AdmissionAttempt.objects.create(
        admission=admission,
        request_id=uuid4(),
        attempt_id=uuid4(),
        status=AttemptStatus.ADMITTED,
        expires_at=timezone.now() + timedelta(minutes=10),
        participant_sid=f"sid-{user.slug}",
    )
    AdmissionPermissionSync.objects.create(
        admission=admission,
        desired_admitted=True,
        revision=1,
        applied_revision=1,
        participant_sid=attempt.participant_sid,
    )
    return admission, attempt


def test_reconcile_excludes_pending_and_preserves_disconnected_activated_order(room_context):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    activate(session, member)
    room.talking_order = [keeper.slug, pending.slug, member.slug]
    room.save(update_fields=["talking_order"])
    state = apply_event(
        session.slug,
        keeper.slug,
        EmptyRoomEvent(),
        None,
        {keeper.slug, pending.slug},
        participant_sids={keeper.slug: f"sid-{keeper.slug}"},
    )
    assert state.talking_order == [keeper.slug, member.slug]


def test_over_capacity_excludes_members_from_turns_but_retains_order(room_context):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    activate(session, member)
    session.seats = 1
    session.save(update_fields=["seats"])
    room.session.seats = 1
    sids = {keeper.slug: f"sid-{keeper.slug}", member.slug: f"sid-{member.slug}"}
    projection = participant_projection(room, set(sids), sids)
    assert projection.retained == {keeper.slug, member.slug}
    assert projection.connected == {keeper.slug}
    with pytest.raises(TransitionError) as error:
        apply_event(session.slug, member.slug, PassStickEvent(), None, set(sids), participant_sids=sids)
    assert error.value.code == ErrorCode.NOT_IN_ROOM
    session.seats = 2
    session.save(update_fields=["seats"])
    room.session.seats = 2
    assert participant_projection(room, set(sids), sids).connected == set(sids)


@pytest.mark.parametrize("condition", ["inactive", "not_attendee"])
def test_keeper_turn_projection_requires_active_attendee(room_context, condition):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    if condition == "inactive":
        keeper.is_active = False
        keeper.save(update_fields=["is_active"])
    else:
        session.attendees.remove(keeper)
    projection = participant_projection(room, {keeper.slug}, {keeper.slug: f"sid-{keeper.slug}"})
    assert keeper.slug not in projection.retained
    assert keeper.slug not in projection.connected


def test_record_join_requires_activated_receipt(room_context):
    session, room, keeper, member, pending = room_context
    SessionAdmission.objects.create(session=session, user=member, state=AdmissionState.ADMITTED)
    with pytest.raises(TransitionError) as error:
        record_join(session, member)
    assert error.value.code == ErrorCode.NOT_JOINABLE
    assert not session.joined.filter(pk=member.pk).exists()


def test_record_join_rejects_keeper_without_activation(room_context):
    session, room, keeper, member, pending = room_context
    with pytest.raises(TransitionError) as error:
        record_join(session, keeper)
    assert error.value.code == ErrorCode.NOT_JOINABLE
    assert not session.joined.filter(pk=keeper.pk).exists()


@pytest.mark.parametrize("target_kind", ["unknown", "foreign", "attendee", "admission"])
def test_ban_requires_session_association_when_enforced(room_context, target_kind):
    session, room, keeper, member, pending = room_context
    target = UserFactory() if target_kind != "unknown" else None
    if target_kind == "attendee":
        session.attendees.add(target)
    elif target_kind == "admission":
        SessionAdmission.objects.create(session=session, user=target)
    slug = target.slug if target else "unknown-identity"
    with patch("totem.rooms.admission.revoke_removed_user") as revoke:
        if target_kind in {"unknown", "foreign"}:
            with pytest.raises(TransitionError) as error:
                apply_event(session.slug, keeper.slug, BanParticipantEvent(participant_slug=slug), None, None)
            assert error.value.code == ErrorCode.NOT_IN_ROOM
            revoke.assert_not_called()
            room.refresh_from_db()
            assert slug not in room.banned_participants
        else:
            state = apply_event(session.slug, keeper.slug, BanParticipantEvent(participant_slug=slug), None, None)
            assert slug in state.banned_participants
            revoke.assert_called_once_with(session, keeper, target, prune=False)


def test_reconnecting_member_retained_but_not_connected_until_latest_activation(room_context):
    session, room, keeper, member, pending = room_context
    admission, attempt = activate(session, member)
    AdmissionAttempt.objects.create(
        admission=admission,
        request_id=uuid4(),
        attempt_id=uuid4(),
        status=AttemptStatus.GRANTING,
        expires_at=timezone.now() + timedelta(minutes=10),
        participant_sid="new-sid",
    )
    projection = participant_projection(room, {member.slug, pending.slug})
    assert projection.retained == {member.slug}
    assert projection.connected == set()


def test_projection_requires_matching_current_permission_proof(room_context):
    session, room, keeper, member, pending = room_context
    admission, attempt = activate(session, member)
    sync = admission.permission_sync
    sync.participant_sid = "different-sid"
    sync.save(update_fields=["participant_sid"])
    projection = participant_projection(room, {member.slug})
    assert projection.retained == {member.slug}
    assert projection.connected == set()


def test_offline_keeper_can_end_but_unavailable_presence_rejects_start(room_context):
    session, room, keeper, member, pending = room_context
    with pytest.raises(TransitionError) as error:
        apply_event(session.slug, keeper.slug, StartRoomEvent(), None, None)
    assert error.value.code == ErrorCode.LIVEKIT_ERROR
    state = apply_event(session.slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), None, None)
    assert state.status == "ended"


def test_pending_cannot_issue_event_or_be_reordered(room_context):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    with pytest.raises(TransitionError) as error:
        apply_event(
            session.slug,
            pending.slug,
            StartRoomEvent(),
            None,
            {keeper.slug, pending.slug},
            participant_sids={keeper.slug: f"sid-{keeper.slug}"},
        )
    assert error.value.code == ErrorCode.NOT_IN_ROOM
    with pytest.raises(TransitionError) as error:
        apply_event(
            session.slug,
            keeper.slug,
            ReorderEvent(talking_order=[pending.slug]),
            None,
            {keeper.slug, pending.slug},
            participant_sids={keeper.slug: f"sid-{keeper.slug}"},
        )
    assert error.value.code == ErrorCode.INVALID_PARTICIPANT_ORDER


@pytest.mark.parametrize("event", [PassStickEvent(), AcceptStickEvent()])
def test_replacement_sid_cannot_send_turn_events(room_context, event):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    activate(session, member)
    room.status = RoomStatus.ACTIVE
    room.turn_state = TurnState.PASSING
    room.talking_order = [keeper.slug, member.slug]
    room.current_speaker = keeper.slug
    room.next_speaker = member.slug
    room.save()
    before = room.to_state()
    with pytest.raises(TransitionError) as error:
        apply_event(
            session.slug,
            member.slug,
            event,
            None,
            {keeper.slug, member.slug},
            participant_sids={keeper.slug: f"sid-{keeper.slug}", member.slug: "replacement"},
        )
    assert error.value.code == ErrorCode.NOT_IN_ROOM
    room.refresh_from_db()
    assert room.to_state() == before


def test_replacement_sid_cannot_be_reorder_target_or_next_speaker(room_context):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    activate(session, member)
    room.talking_order = [keeper.slug, member.slug]
    room.save(update_fields=["talking_order"])
    sids = {keeper.slug: f"sid-{keeper.slug}", member.slug: "replacement"}
    projection = participant_projection(room, {keeper.slug, member.slug}, sids)
    assert member.slug in projection.retained
    assert member.slug not in projection.connected
    with pytest.raises(TransitionError) as error:
        apply_event(
            session.slug,
            keeper.slug,
            ReorderEvent(talking_order=[keeper.slug, member.slug]),
            None,
            set(sids),
            participant_sids=sids,
        )
    assert error.value.code == ErrorCode.INVALID_PARTICIPANT_ORDER
    state = apply_event(session.slug, keeper.slug, StartRoomEvent(), None, set(sids), participant_sids=sids)
    assert state.next_speaker == keeper.slug


def test_keeper_replacement_sid_cannot_start(room_context):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    with pytest.raises(TransitionError) as error:
        apply_event(
            session.slug,
            keeper.slug,
            StartRoomEvent(),
            None,
            {keeper.slug},
            participant_sids={keeper.slug: "replacement"},
        )
    assert error.value.code == ErrorCode.KEEPER_NOT_IN_ROOM


def test_reorder_keeps_disconnected_member_and_verified_speaker(room_context):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    activate(session, member)
    room.status = RoomStatus.ACTIVE
    room.turn_state = TurnState.SPEAKING
    room.talking_order = [keeper.slug, member.slug]
    room.current_speaker = keeper.slug
    room.next_speaker = keeper.slug
    room.save()
    state = apply_event(
        session.slug,
        keeper.slug,
        ReorderEvent(talking_order=[member.slug, keeper.slug]),
        None,
        {keeper.slug},
        participant_sids={keeper.slug: f"sid-{keeper.slug}"},
    )
    assert state.talking_order == [keeper.slug, member.slug]
    assert state.next_speaker == keeper.slug


def test_missing_sid_snapshot_rejects_presence_based_event(room_context):
    session, room, keeper, member, pending = room_context
    with pytest.raises(TransitionError) as error:
        apply_event(session.slug, keeper.slug, EmptyRoomEvent(), None, set())
    assert error.value.code == ErrorCode.LIVEKIT_ERROR


def test_former_keeper_without_durable_admission_loses_projection(room_context):
    session, room, keeper, member, pending = room_context
    activate(session, keeper, AdmissionState.NONE)
    room.keeper = member.slug
    projection = participant_projection(room, {keeper.slug})
    assert keeper.slug not in projection.retained
    assert keeper.slug not in projection.connected


def test_empty_projection_clears_invalid_speakers_but_keeps_disconnected_members(room_context):
    session, room, keeper, member, pending = room_context
    activate(session, member)
    room.status = RoomStatus.ACTIVE
    room.turn_state = TurnState.SPEAKING
    room.talking_order = [member.slug, pending.slug]
    room.current_speaker = pending.slug
    room.next_speaker = pending.slug
    room.save()
    state = apply_event(session.slug, keeper.slug, EmptyRoomEvent(), None, set(), participant_sids={})
    assert state.talking_order == [member.slug]
    assert state.current_speaker is None
    assert state.next_speaker is None
    assert state.turn_state == TurnState.IDLE


def test_flag_off_keeps_legacy_raw_presence(room_context, settings):
    session, room, keeper, member, pending = room_context
    settings.SERVER_ENFORCED_ADMISSION = False
    room.talking_order = [keeper.slug]
    room.save(update_fields=["talking_order"])
    state = apply_event(session.slug, keeper.slug, EmptyRoomEvent(), None, {keeper.slug, pending.slug})
    assert state.talking_order == [keeper.slug, pending.slug]


def test_join_analytics_only_after_first_committed_activation(room_context, django_capture_on_commit_callbacks):
    session, room, keeper, member, pending = room_context
    activate(session, member)
    with patch("totem.users.analytics.event_joined") as joined, patch("totem.rooms.state_machine.publish_state"):
        with django_capture_on_commit_callbacks(execute=True):
            record_join(session, member)
            record_join(session, member)
            joined.assert_not_called()
        joined.assert_called_once()
