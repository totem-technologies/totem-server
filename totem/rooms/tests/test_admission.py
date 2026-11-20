import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection, connections
from django.utils import timezone
from livekit import api

from totem.rooms import admission as capacity_admission
from totem.rooms import livekit
from totem.rooms.admission import http as admission_http
from totem.rooms.admission.capacity import admission_limit
from totem.rooms.admission.schemas import BatchCommandInput, SettingsCommandInput
from totem.rooms.livekit import LiveKitPermissionError
from totem.rooms.models import AdmissionAttempt, AdmissionState, AttemptStatus, Room, SessionAdmission
from totem.rooms.schemas import EndReason, EndRoomEvent
from totem.rooms.state_machine import apply_event
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory


def test_new_room_requires_approval_by_default():
    room = Room()
    assert room.approval_required is True
    assert room.admission_revision == 0


@pytest.fixture
def admission():
    from totem.rooms import admission

    return admission


@pytest.fixture
def context(db):
    keeper = UserFactory()
    user = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() + timedelta(minutes=5))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    return session, room, keeper, user


@pytest.fixture
def livekit_permissions():
    participant = api.ParticipantInfo(
        sid="participant-1",
        permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
    )
    with (
        patch("totem.rooms.admission.permissions.get_participant_snapshot", return_value=participant),
        patch("totem.rooms.admission.permissions.update_participant_permissions", return_value=participant),
        patch("totem.rooms.admission.permissions.hard_disconnect_participant"),
        patch("totem.rooms.state_machine.publish_state"),
    ):
        yield


@pytest.fixture
def clear_content_type_cache(transactional_db):
    ContentType.objects.clear_cache()
    yield
    ContentType.objects.clear_cache()


def request(admission, session, user):
    return admission.request_admission(session.slug, user, uuid4(), uuid4())


def decide(admission, room, keeper, attempt, decision):
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


def set_policy(admission, room, keeper, required):
    room.refresh_from_db()
    return admission.update_approval_required(
        room.session.slug,
        keeper,
        required,
        expected_revision=room.admission_revision,
        expected_room_version=room.state_version,
    )


def assert_error(admission, code, operation):
    with pytest.raises(admission.AdmissionError) as error:
        operation()
    assert error.value.code == code


def test_request_waits_until_twenty_minutes_after_start(admission, context):
    session, _, _, user = context
    attempt = request(admission, session, user)
    assert attempt.status == "pending"
    assert attempt.admission.session_id == session.pk
    assert attempt.admission.user_id == user.pk
    assert attempt.expires_at == session.start + timedelta(minutes=20)
    assert not admission.is_authorized_to_enter(session.slug, user)
    assert admission.get_admission(session.slug, user).state == "none"


def test_request_for_started_session_expires_twenty_minutes_from_now(admission, context):
    session, _, _, user = context
    session.start = timezone.now() - timedelta(minutes=1)
    session.save(update_fields=["start"])
    before = timezone.now()
    attempt = request(admission, session, user)
    after = timezone.now()
    assert before + timedelta(minutes=20) <= attempt.expires_at <= after + timedelta(minutes=20)


@pytest.mark.parametrize("eligibility", ["not_attending", "inactive", "too_early", "cancelled"])
def test_request_rejects_ineligible_user(admission, context, eligibility):
    session, _, _, user = context
    if eligibility == "not_attending":
        session.attendees.remove(user)
    elif eligibility == "inactive":
        user.is_active = False
        user.save(update_fields=["is_active"])
    elif eligibility == "too_early":
        session.start = timezone.now() + timedelta(hours=2)
        session.save(update_fields=["start"])
    else:
        session.cancelled = True
        session.save(update_fields=["cancelled"])
    assert_error(admission, "not_eligible", lambda: request(admission, session, user))


def test_keeper_skips_approval_but_not_join_eligibility(admission, context):
    session, _, keeper, _ = context
    assert admission.is_authorized_to_enter(session.slug, keeper)
    session.attendees.remove(keeper)
    assert not admission.is_authorized_to_enter(session.slug, keeper)


@pytest.mark.django_db(transaction=True)
def test_approve_grant_and_complete(admission, context, livekit_permissions):
    session, room, keeper, user = context
    attempt = request(admission, session, user)
    waiting_deadline = attempt.expires_at
    before = timezone.now()
    attempt = decide(admission, room, keeper, attempt, "approve")
    after = timezone.now()
    assert attempt.status == "granting"
    assert before + timedelta(minutes=2) <= attempt.expires_at <= after + timedelta(minutes=2)
    assert attempt.expires_at <= waiting_deadline
    assert attempt.decision_actor_id == keeper.pk
    durable = admission.get_admission(session.slug, user)
    assert durable.state == "admitted"
    assert durable.decision_actor_id == keeper.pk
    assert admission.is_authorized_to_enter(session.slug, user)
    attempt = admission.complete_admission(
        session.slug,
        user,
        attempt.request_id,
        attempt.attempt_id,
        expected_version=attempt.version,
    )
    assert attempt.status == "admitted"
    assert admission.get_admission(session.slug, user).state == "admitted"


def test_grant_deadline_does_not_extend_waiting_deadline(admission, context):
    session, room, keeper, user = context
    attempt = request(admission, session, user)
    attempt.expires_at = timezone.now() + timedelta(seconds=30)
    attempt.save(update_fields=["expires_at"])
    deadline = attempt.expires_at
    attempt = decide(admission, room, keeper, attempt, "approve")
    assert attempt.expires_at == deadline


def test_grant_expiry_does_not_erase_durable_admission(admission, context):
    session, room, keeper, user = context
    attempt = decide(admission, room, keeper, request(admission, session, user), "approve")
    attempt.expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=["expires_at"])
    try:
        result = admission.complete_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )
        assert result.status != "admitted"
    except admission.AdmissionError:
        pass
    assert admission.get_admission(session.slug, user).state == "admitted"


def test_duplicate_request_ids_are_idempotent_and_new_ids_supersede_pending(admission, context):
    session, _, keeper, user = context
    first = request(admission, session, user)
    duplicate = admission.request_admission(session.slug, user, first.request_id, first.attempt_id)
    assert duplicate.pk == first.pk
    second = request(admission, session, user)
    first.refresh_from_db()
    assert first.status == "superseded"
    assert second.status == "pending"
    replay = admission.request_admission(session.slug, user, first.request_id, first.attempt_id)
    assert replay.status == "superseded"
    assert [attempt.pk for attempt in admission.pending_queue(session.slug, keeper)] == [second.pk]


def test_decline_allows_new_explicit_request_and_supersedes_old_ids(admission, context):
    session, room, keeper, user = context
    first = request(admission, session, user)
    declined = decide(admission, room, keeper, first, "decline")
    assert declined.status == "declined"
    second = request(admission, session, user)
    assert second.status == "pending"
    old = admission.request_admission(session.slug, user, first.request_id, first.attempt_id)
    assert old.status != "pending"
    assert admission.pending_queue(session.slug, keeper)[0].pk == second.pk


def test_permanent_decline_overrides_disabled_policy_until_explicitly_allowed(admission, context):
    session, room, keeper, user = context
    attempt = decide(admission, room, keeper, request(admission, session, user), "permanently_decline")
    assert attempt.status == "permanently_declined"
    durable = admission.get_admission(session.slug, user)
    assert durable.state == "permanently_declined"
    set_policy(admission, room, keeper, False)
    assert not admission.is_authorized_to_enter(session.slug, user)
    assert_error(admission, "not_eligible", lambda: request(admission, session, user))
    room.refresh_from_db()
    durable = admission.allow_previously_declined(
        session.slug,
        keeper,
        user,
        expected_version=durable.version,
        expected_room_version=room.state_version,
    )
    assert durable.state == "none"
    attempt.refresh_from_db()
    assert attempt.status == "permanently_declined"
    assert not admission.is_authorized_to_enter(session.slug, user)
    new_attempt = request(admission, session, user)
    assert new_attempt.status == "granting"
    assert admission.get_admission(session.slug, user).state == "admitted"
    assert admission.is_authorized_to_enter(session.slug, user)


def test_disabled_policy_auto_grants_only_after_request(admission, context):
    session, room, keeper, user = context
    set_policy(admission, room, keeper, False)
    assert admission.get_admission(session.slug, user) is None
    assert not admission.is_authorized_to_enter(session.slug, user)
    attempt = request(admission, session, user)
    assert attempt.status == "granting"
    assert admission.get_admission(session.slug, user).state == "admitted"
    assert admission.is_authorized_to_enter(session.slug, user)
    session.attendees.remove(user)
    assert not admission.is_authorized_to_enter(session.slug, user)


def test_disabling_policy_auto_grants_only_eligible_pending_attempts(admission, context):
    session, room, keeper, user = context
    ineligible = UserFactory()
    session.attendees.add(ineligible)
    eligible_attempt = request(admission, session, user)
    ineligible_attempt = request(admission, session, ineligible)
    session.attendees.remove(ineligible)
    updated = set_policy(admission, room, keeper, False)
    eligible_attempt.refresh_from_db()
    ineligible_attempt.refresh_from_db()
    assert updated.approval_required is False
    assert eligible_attempt.status == "granting"
    assert admission.get_admission(session.slug, user).state == "admitted"
    assert admission.is_authorized_to_enter(session.slug, user)
    assert ineligible_attempt.status != "granting"
    assert admission.get_admission(session.slug, ineligible).state != "admitted"
    assert not admission.is_authorized_to_enter(session.slug, ineligible)


def test_enabling_policy_preserves_durable_admission(admission, context):
    session, room, keeper, user = context
    set_policy(admission, room, keeper, False)
    attempt = request(admission, session, user)
    assert attempt.status == "granting"
    updated = set_policy(admission, room, keeper, True)
    assert updated.approval_required is True
    assert admission.get_admission(session.slug, user).state == "admitted"
    assert admission.is_authorized_to_enter(session.slug, user)


def test_policy_survives_room_reload_and_keeper_reassignment(admission, context):
    session, room, keeper, user = context
    updated = set_policy(admission, room, keeper, False)
    revision = updated.admission_revision
    new_keeper = UserFactory()
    session.attendees.add(new_keeper)
    room.refresh_from_db()
    room.keeper = new_keeper.slug
    room.save(update_fields=["keeper"])
    room = Room.objects.get(pk=room.pk)
    assert room.approval_required is False
    assert room.admission_revision == revision
    assert_error(admission, "not_keeper", lambda: set_policy(admission, room, keeper, True))
    assert_error(admission, "not_keeper", lambda: admission.pending_queue(session.slug, keeper))
    updated = set_policy(admission, room, new_keeper, True)
    assert updated.approval_required is True
    assert updated.admission_revision == revision + 1
    assert not admission.is_authorized_to_enter(session.slug, user)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("departure", ["cancelled", "completed"])
def test_durable_admission_auto_grants_return_after_cancel_or_normal_leave(
    admission, context, departure, livekit_permissions
):
    session, room, keeper, user = context
    attempt = decide(admission, room, keeper, request(admission, session, user), "approve")
    if departure == "cancelled":
        attempt = admission.cancel_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )
        assert attempt.status == "cancelled"
    else:
        attempt = admission.complete_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )
        assert attempt.status == "admitted"
    assert admission.get_admission(session.slug, user).state == "admitted"
    returning = request(admission, session, user)
    assert returning.status == "granting"
    assert admission.is_authorized_to_enter(session.slug, user)


def test_new_request_after_removal_requires_approval(admission, context):
    session, room, keeper, user = context
    decide(admission, room, keeper, request(admission, session, user), "approve")
    durable = admission.get_admission(session.slug, user)
    room.refresh_from_db()
    admission.revoke_admission(
        session.slug,
        keeper,
        user,
        expected_version=durable.version,
        expected_room_version=room.state_version,
    )
    assert not admission.is_authorized_to_enter(session.slug, user)
    attempt = request(admission, session, user)
    assert attempt.status == "pending"
    assert not admission.is_authorized_to_enter(session.slug, user)


@pytest.mark.parametrize("terminal", ["expired", "cancelled", "superseded"])
def test_keeper_cannot_decide_terminal_attempt(admission, context, terminal):
    session, room, keeper, user = context
    attempt = request(admission, session, user)
    if terminal == "expired":
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        admission.pending_queue(session.slug, keeper)
    elif terminal == "cancelled":
        admission.cancel_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )
    else:
        request(admission, session, user)
    attempt.refresh_from_db()
    assert attempt.status == terminal
    assert_error(admission, "invalid_attempt", lambda: decide(admission, room, keeper, attempt, "approve"))
    attempt.refresh_from_db()
    assert attempt.status == terminal
    assert not admission.is_authorized_to_enter(session.slug, user)


def test_revoke_removes_access_and_revokes_active_attempt(admission, context):
    session, room, keeper, user = context
    attempt = decide(admission, room, keeper, request(admission, session, user), "approve")
    durable = admission.get_admission(session.slug, user)
    room.refresh_from_db()
    durable = admission.revoke_admission(
        session.slug,
        keeper,
        user,
        expected_version=durable.version,
        expected_room_version=room.state_version,
    )
    attempt.refresh_from_db()
    assert durable.state == "revoked"
    assert attempt.status == "revoked"
    assert not admission.is_authorized_to_enter(session.slug, user)


def test_stale_revoke_does_not_change_admission(admission, context):
    session, room, keeper, user = context
    decide(admission, room, keeper, request(admission, session, user), "approve")
    durable = admission.get_admission(session.slug, user)
    room.refresh_from_db()
    for version, room_version in [(durable.version + 1, room.state_version), (durable.version, room.state_version + 1)]:
        assert_error(
            admission,
            "stale_version",
            lambda: admission.revoke_admission(
                session.slug,
                keeper,
                user,
                expected_version=version,
                expected_room_version=room_version,
            ),
        )
    assert admission.get_admission(session.slug, user).state == "admitted"


def test_cancel_is_owned_by_requesting_user(admission, context):
    session, _, _, user = context
    other = UserFactory()
    session.attendees.add(other)
    attempt = request(admission, session, user)
    assert_error(
        admission,
        "invalid_attempt",
        lambda: admission.cancel_admission(
            session.slug,
            other,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        ),
    )
    assert_error(
        admission,
        "stale_version",
        lambda: admission.cancel_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version + 1,
        ),
    )
    cancelled = admission.cancel_admission(
        session.slug,
        user,
        attempt.request_id,
        attempt.attempt_id,
        expected_version=attempt.version,
    )
    assert cancelled.status == "cancelled"
    assert not admission.is_authorized_to_enter(session.slug, user)


def test_keeper_only_operations_reject_attendee(admission, context):
    session, room, _, user = context
    attempt = request(admission, session, user)
    assert_error(admission, "not_keeper", lambda: decide(admission, room, user, attempt, "approve"))
    assert_error(admission, "not_keeper", lambda: set_policy(admission, room, user, False))
    assert_error(admission, "not_keeper", lambda: admission.pending_queue(session.slug, user))


def test_stale_attempt_and_room_versions_leave_request_pending(admission, context):
    session, room, keeper, user = context
    attempt = request(admission, session, user)
    room.refresh_from_db()
    for version, room_version in [(attempt.version + 1, room.state_version), (attempt.version, room.state_version + 1)]:
        assert_error(
            admission,
            "stale_version",
            lambda: admission.decide_admission(
                session.slug,
                keeper,
                attempt.request_id,
                attempt.attempt_id,
                "approve",
                expected_version=version,
                expected_room_version=room_version,
            ),
        )
    attempt.refresh_from_db()
    assert attempt.status == "pending"
    assert not admission.is_authorized_to_enter(session.slug, user)


def test_stale_policy_revision_and_room_version_do_not_change_policy(admission, context):
    session, room, keeper, _ = context
    for revision, version in [
        (room.admission_revision + 1, room.state_version),
        (room.admission_revision, room.state_version + 1),
    ]:
        assert_error(
            admission,
            "stale_version",
            lambda: admission.update_approval_required(
                session.slug,
                keeper,
                False,
                expected_revision=revision,
                expected_room_version=version,
            ),
        )
    room.refresh_from_db()
    assert room.approval_required is True


def test_ending_room_invalidates_pending_and_granting_attempts(admission, context):
    session, room, keeper, user = context
    other = UserFactory()
    session.attendees.add(other)
    pending = request(admission, session, user)
    granting = decide(admission, room, keeper, request(admission, session, other), "approve")
    room.refresh_from_db()
    apply_event(
        session.slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), room.state_version, {keeper.slug}
    )
    pending.refresh_from_db()
    granting.refresh_from_db()
    assert pending.status not in {"pending", "granting"}
    assert granting.status not in {"pending", "granting"}
    assert not admission.is_authorized_to_enter(session.slug, user)
    assert not admission.is_authorized_to_enter(session.slug, other)
    assert_error(admission, "ended", lambda: request(admission, session, user))


def run_concurrently(operation):
    barrier = Barrier(2)

    def run():
        try:
            barrier.wait(timeout=10)
            return operation()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        return [future.result(timeout=20) for future in futures]


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_request_is_idempotent(admission, clear_content_type_cache, livekit_permissions):
    keeper = UserFactory()
    user = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() + timedelta(minutes=5))
    session.attendees.add(keeper, user)
    Room.objects.get_or_create_for_session(session)
    request_id, attempt_id = uuid4(), uuid4()
    results = run_concurrently(lambda: admission.request_admission(session.slug, user, request_id, attempt_id))
    assert results[0].pk == results[1].pk
    assert results[0].status == results[1].status == "pending"
    assert len(admission.pending_queue(session.slug, keeper)) == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_conflicting_decisions_have_one_winner(admission, clear_content_type_cache, livekit_permissions):
    keeper = UserFactory()
    user = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() + timedelta(minutes=5))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    attempt = request(admission, session, user)
    room.refresh_from_db()
    decisions = iter(["approve", "permanently_decline"])

    def decide_once():
        decision = next(decisions)
        try:
            result = admission.decide_admission(
                session.slug,
                keeper,
                attempt.request_id,
                attempt.attempt_id,
                decision,
                expected_version=attempt.version,
                expected_room_version=room.state_version,
            )
            return result.status
        except admission.AdmissionError as error:
            return error.code

    results = run_concurrently(decide_once)
    assert results.count("stale_version") == 1
    assert len(set(results) & {"granting", "permanently_declined"}) == 1
    attempt.refresh_from_db()
    durable = admission.get_admission(session.slug, user)
    assert (attempt.status, durable.state) in {
        ("granting", "admitted"),
        ("permanently_declined", "permanently_declined"),
    }


@pytest.fixture
def capacity_context(settings):
    settings.LIVEKIT_API_KEY = "test-key-test-key-test-key-test-key"
    settings.LIVEKIT_API_SECRET = "test-secret-test-secret-test-secret-test-secret-test-secret"
    keeper = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper)
    room = Room.objects.get_or_create_for_session(session)

    def missing(*args, **kwargs):
        assert not connection.in_atomic_block
        raise LiveKitPermissionError("participant_missing", "Not connected")

    with (
        patch("totem.rooms.admission.permissions.get_participant_snapshot", side_effect=missing),
        patch("totem.rooms.state_machine.publish_state"),
    ):
        yield session, room, keeper


def add_users(session, count):
    users = [UserFactory() for _ in range(count)]
    session.attendees.add(*users)
    return users


def capacity_request(session, user):
    return capacity_admission.request_admission(session.slug, user, uuid4(), uuid4())


def approve(room, keeper, attempt):
    return capacity_admission.decide_admission(
        room.session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        "approve",
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )


@pytest.mark.django_db(transaction=True)
def test_default_empty_room_requires_approval(capacity_context):
    session, room, _ = capacity_context
    (user,) = add_users(session, 1)
    assert room.approval_required is True
    result = capacity_admission.prepare_admission_join(session.slug, user, connected=set())
    assert result.admission is not None
    assert result.admission.status == AttemptStatus.PENDING
    assert result.admission.permissions == "waiting"
    assert not session.joined.filter(pk=user.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_keeper_token_does_not_record_join(capacity_context):
    session, _, keeper = capacity_context
    result = capacity_admission.prepare_admission_join(session.slug, keeper, connected=set())
    assert result.admission is not None
    assert result.admission.permissions == "admitted"
    assert result.admission.status == AttemptStatus.GRANTING
    assert not session.joined.filter(pk=keeper.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_empty_room_reserves_only_seat_for_keeper(capacity_context):
    session, room, keeper = capacity_context
    session.seats = 1
    session.save(update_fields=["seats"])
    (user,) = add_users(session, 1)
    attempt = capacity_request(session, user)
    with pytest.raises(capacity_admission.AdmissionError) as error:
        approve(room, keeper, attempt)
    assert error.value.code == "admission_full"
    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.PENDING
    assert attempt.admission.state == AdmissionState.NONE


@pytest.mark.parametrize(("seats", "limit"), [(0, 1), (1, 1), (8, 8), (100, 10)])
@pytest.mark.django_db(transaction=True)
def test_admission_limit_includes_keeper_and_is_clamped(capacity_context, seats, limit):
    _, room, _ = capacity_context
    room.session.seats = seats
    assert admission_limit(room) == limit


@pytest.mark.django_db(transaction=True)
def test_policy_off_keeps_full_and_removed_requests_pending(capacity_context):
    session, room, keeper = capacity_context
    session.seats = 2
    session.save(update_fields=["seats"])
    admitted, removed, newcomer = add_users(session, 3)
    SessionAdmission.objects.create(session=session, user=admitted, state=AdmissionState.ADMITTED)
    SessionAdmission.objects.create(session=session, user=removed, state=AdmissionState.REVOKED)
    old = capacity_request(session, removed)
    room.refresh_from_db()
    capacity_admission.update_approval_required(
        session.slug, keeper, False, expected_revision=room.admission_revision, expected_room_version=room.state_version
    )
    old.refresh_from_db()
    assert old.status == AttemptStatus.PENDING
    new = capacity_request(session, newcomer)
    assert new.status == AttemptStatus.PENDING
    SessionAdmission.objects.filter(session=session, user=admitted).update(state=AdmissionState.REVOKED)
    retry = capacity_admission.request_admission(session.slug, removed, old.request_id, old.attempt_id)
    assert retry.status == AttemptStatus.PENDING
    room.refresh_from_db()
    assert approve(room, keeper, retry).status == AttemptStatus.GRANTING


@pytest.mark.parametrize("action", ["admit_all", "settings"])
@pytest.mark.django_db(transaction=True)
def test_batch_capacity_reports_per_person_and_snapshot_excludes_waiters(capacity_context, action):
    session, room, keeper = capacity_context
    session.seats = 2
    session.save(update_fields=["seats"])
    first, second = add_users(session, 2)
    for user in (first, second):
        capacity_admission.prepare_admission_join(session.slug, user, connected=set())
    room.refresh_from_db()
    if action == "admit_all":
        body = BatchCommandInput(command_id=uuid4(), expected_room_version=room.state_version)
    else:
        body = SettingsCommandInput(
            command_id=uuid4(),
            expected_room_version=room.state_version,
            expected_revision=room.admission_revision,
            approval_required=False,
        )
    with patch.object(admission_http, "get_admission_participants", return_value={first.slug, second.slug}):
        response = admission_http.execute_keeper_command(session.slug, keeper, action, body)
    results = {item.identity: item for item in response.results}
    assert results[first.slug].outcome == "approved"
    assert results[first.slug].error is None
    assert results[second.slug].outcome == "skipped"
    assert results[second.slug].error == "admission_full"
    assert response.partial_failure
    assert response.snapshot.admission_capacity == 2
    assert response.snapshot.admission_slots_used == 2
    assert response.snapshot.waiting_slots_used == 1
    assert [item.identity for item in response.snapshot.waiting] == [second.slug]
    assert (
        AdmissionAttempt.objects.get(admission__session=session, admission__user=second).status == AttemptStatus.PENDING
    )


@pytest.mark.django_db(transaction=True)
def test_removed_new_request_stays_pending_when_policy_already_off(capacity_context):
    session, room, keeper = capacity_context
    (user,) = add_users(session, 1)
    member = SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.REVOKED)
    capacity_admission.update_approval_required(
        session.slug, keeper, False, expected_revision=room.admission_revision, expected_room_version=room.state_version
    )
    first = capacity_request(session, user)
    room.refresh_from_db()
    capacity_admission.update_approval_required(
        session.slug, keeper, False, expected_revision=room.admission_revision, expected_room_version=room.state_version
    )
    second = capacity_request(session, user)
    first.refresh_from_db()
    member.refresh_from_db()
    assert first.status == AttemptStatus.SUPERSEDED
    assert second.status == AttemptStatus.PENDING
    assert member.state == AdmissionState.REVOKED
    room.refresh_from_db()
    assert approve(room, keeper, second).status == AttemptStatus.GRANTING
    member.refresh_from_db()
    assert member.state == AdmissionState.ADMITTED


@pytest.mark.django_db(transaction=True)
def test_waiting_limit_retains_request_and_refresh_does_not_use_extra_slot(capacity_context):
    session, _, _ = capacity_context
    users = add_users(session, 6)
    before = timezone.now()
    responses = [capacity_admission.prepare_admission_join(session.slug, user, connected=set()) for user in users[:5]]
    after = timezone.now()
    attempts = list(AdmissionAttempt.objects.filter(admission__session=session))
    assert len(attempts) == 5
    assert all(before + timedelta(seconds=60) <= a.token_expires_at <= after + timedelta(seconds=60) for a in attempts)
    capacity_admission.prepare_admission_join(session.slug, users[0], connected=set())
    with pytest.raises(capacity_admission.AdmissionError) as error:
        capacity_admission.prepare_admission_join(session.slug, users[5], connected=set())
    assert error.value.code == "waiting_full"
    assert (
        AdmissionAttempt.objects.get(admission__session=session, admission__user=users[5]).status
        == AttemptStatus.PENDING
    )
    assert len(responses) == 5


@pytest.mark.django_db(transaction=True)
def test_raw_presence_counts_waiters_and_an_expired_lease_is_reusable(capacity_context):
    session, _, _ = capacity_context
    first, second = add_users(session, 2)
    capacity_admission.prepare_admission_join(session.slug, first, connected=set())
    attempt = AdmissionAttempt.objects.get(admission__session=session, admission__user=first)
    attempt.token_expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=["token_expires_at"])
    raw = {f"waiting-{i}" for i in range(5)}
    with pytest.raises(capacity_admission.AdmissionError) as error:
        capacity_admission.prepare_admission_join(session.slug, second, connected=raw)
    assert error.value.code == "waiting_full"
    result = capacity_admission.prepare_admission_join(session.slug, second, connected=set())
    assert result.admission is not None
    assert result.admission.permissions == "waiting"


@pytest.mark.django_db(transaction=True)
def test_physical_full_keeps_admitted_request(capacity_context):
    session, _, keeper = capacity_context
    (user,) = add_users(session, 1)
    SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
    connected = {keeper.slug} | {f"occupant-{i}" for i in range(14)}
    with pytest.raises(capacity_admission.AdmissionError) as error:
        capacity_admission.prepare_admission_join(session.slug, user, connected=connected)
    assert error.value.code == "room_full"
    assert (
        AdmissionAttempt.objects.get(admission__session=session, admission__user=user).status == AttemptStatus.GRANTING
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_approvals_compete_for_last_seat(capacity_context):
    session, room, keeper = capacity_context
    session.seats = 2
    session.save(update_fields=["seats"])
    attempts = [capacity_request(session, user) for user in add_users(session, 2)]
    barrier = Barrier(2)

    def worker(attempt):
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            try:
                return approve(room, keeper, attempt).status
            except capacity_admission.AdmissionError as error:
                return error.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, attempts))
    assert sorted(results) == ["admission_full", AttemptStatus.GRANTING]
    assert SessionAdmission.objects.filter(session=session, state=AdmissionState.ADMITTED).count() == 1
    assert AdmissionAttempt.objects.filter(admission__session=session, status=AttemptStatus.PENDING).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_waiting_tokens_never_exceed_five(capacity_context):
    session, _, _ = capacity_context
    users = add_users(session, 6)
    barrier = Barrier(6)

    def worker(user):
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            try:
                capacity_admission.prepare_admission_join(session.slug, user, connected=set())
                return "issued"
            except capacity_admission.AdmissionError as error:
                return error.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(worker, users))
    assert results.count("issued") == 5
    assert results.count("waiting_full") == 1
    assert AdmissionAttempt.objects.filter(admission__session=session, status=AttemptStatus.PENDING).count() == 6
    assert AdmissionAttempt.objects.filter(admission__session=session, token_expires_at__gt=timezone.now()).count() == 5


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
