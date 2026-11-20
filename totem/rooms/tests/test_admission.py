from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connections
from django.utils import timezone
from livekit import api

from totem.rooms.models import Room
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
