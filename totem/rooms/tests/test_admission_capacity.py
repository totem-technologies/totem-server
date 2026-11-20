from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import connection, connections
from django.utils import timezone

from totem.rooms import admission
from totem.rooms.admission import http as admission_http
from totem.rooms.admission.capacity import admission_limit
from totem.rooms.admission.schemas import BatchCommandInput, SettingsCommandInput
from totem.rooms.livekit import LiveKitPermissionError
from totem.rooms.models import AdmissionAttempt, AdmissionState, AttemptStatus, Room, SessionAdmission
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def context(settings):
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


def request(session, user):
    return admission.request_admission(session.slug, user, uuid4(), uuid4())


def approve(room, keeper, attempt):
    return admission.decide_admission(
        room.session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        "approve",
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )


def test_default_empty_room_requires_approval(context):
    session, room, _ = context
    (user,) = add_users(session, 1)
    assert room.approval_required is True
    result = admission.prepare_admission_join(session.slug, user, connected=set())
    assert result.admission.status == AttemptStatus.PENDING
    assert result.admission.permissions == "waiting"
    assert not session.joined.filter(pk=user.pk).exists()


def test_keeper_token_does_not_record_join(context):
    session, _, keeper = context
    result = admission.prepare_admission_join(session.slug, keeper, connected=set())
    assert result.admission.permissions == "admitted"
    assert result.admission.status == AttemptStatus.GRANTING
    assert not session.joined.filter(pk=keeper.pk).exists()


def test_empty_room_reserves_only_seat_for_keeper(context):
    session, room, keeper = context
    session.seats = 1
    session.save(update_fields=["seats"])
    (user,) = add_users(session, 1)
    attempt = request(session, user)
    with pytest.raises(admission.AdmissionError) as error:
        approve(room, keeper, attempt)
    assert error.value.code == "admission_full"
    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.PENDING
    assert attempt.admission.state == AdmissionState.NONE


@pytest.mark.parametrize(("seats", "limit"), [(0, 1), (1, 1), (8, 8), (100, 10)])
def test_admission_limit_includes_keeper_and_is_clamped(context, seats, limit):
    _, room, _ = context
    room.session.seats = seats
    assert admission_limit(room) == limit


def test_policy_off_keeps_full_and_removed_requests_pending(context):
    session, room, keeper = context
    session.seats = 2
    session.save(update_fields=["seats"])
    admitted, removed, newcomer = add_users(session, 3)
    SessionAdmission.objects.create(session=session, user=admitted, state=AdmissionState.ADMITTED)
    SessionAdmission.objects.create(session=session, user=removed, state=AdmissionState.REVOKED)
    old = request(session, removed)
    room.refresh_from_db()
    admission.update_approval_required(
        session.slug, keeper, False, expected_revision=room.admission_revision, expected_room_version=room.state_version
    )
    old.refresh_from_db()
    assert old.status == AttemptStatus.PENDING
    new = request(session, newcomer)
    assert new.status == AttemptStatus.PENDING
    SessionAdmission.objects.filter(session=session, user=admitted).update(state=AdmissionState.REVOKED)
    retry = admission.request_admission(session.slug, removed, old.request_id, old.attempt_id)
    assert retry.status == AttemptStatus.PENDING
    room.refresh_from_db()
    assert approve(room, keeper, retry).status == AttemptStatus.GRANTING


@pytest.mark.parametrize("action", ["admit_all", "settings"])
def test_batch_capacity_reports_per_person_and_snapshot_excludes_waiters(context, action):
    session, room, keeper = context
    session.seats = 2
    session.save(update_fields=["seats"])
    first, second = add_users(session, 2)
    for user in (first, second):
        admission.prepare_admission_join(session.slug, user, connected=set())
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


def test_removed_new_request_stays_pending_when_policy_already_off(context):
    session, room, keeper = context
    (user,) = add_users(session, 1)
    member = SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.REVOKED)
    admission.update_approval_required(
        session.slug, keeper, False, expected_revision=room.admission_revision, expected_room_version=room.state_version
    )
    first = request(session, user)
    room.refresh_from_db()
    admission.update_approval_required(
        session.slug, keeper, False, expected_revision=room.admission_revision, expected_room_version=room.state_version
    )
    second = request(session, user)
    first.refresh_from_db()
    member.refresh_from_db()
    assert first.status == AttemptStatus.SUPERSEDED
    assert second.status == AttemptStatus.PENDING
    assert member.state == AdmissionState.REVOKED
    room.refresh_from_db()
    assert approve(room, keeper, second).status == AttemptStatus.GRANTING
    member.refresh_from_db()
    assert member.state == AdmissionState.ADMITTED


def test_waiting_limit_retains_request_and_refresh_does_not_use_extra_slot(context):
    session, _, _ = context
    users = add_users(session, 6)
    before = timezone.now()
    responses = [admission.prepare_admission_join(session.slug, user, connected=set()) for user in users[:5]]
    after = timezone.now()
    attempts = list(AdmissionAttempt.objects.filter(admission__session=session))
    assert len(attempts) == 5
    assert all(before + timedelta(seconds=60) <= a.token_expires_at <= after + timedelta(seconds=60) for a in attempts)
    admission.prepare_admission_join(session.slug, users[0], connected=set())
    with pytest.raises(admission.AdmissionError) as error:
        admission.prepare_admission_join(session.slug, users[5], connected=set())
    assert error.value.code == "waiting_full"
    assert (
        AdmissionAttempt.objects.get(admission__session=session, admission__user=users[5]).status
        == AttemptStatus.PENDING
    )
    assert len(responses) == 5


def test_raw_presence_counts_waiters_and_an_expired_lease_is_reusable(context):
    session, _, _ = context
    first, second = add_users(session, 2)
    admission.prepare_admission_join(session.slug, first, connected=set())
    attempt = AdmissionAttempt.objects.get(admission__session=session, admission__user=first)
    attempt.token_expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=["token_expires_at"])
    raw = {f"waiting-{i}" for i in range(5)}
    with pytest.raises(admission.AdmissionError) as error:
        admission.prepare_admission_join(session.slug, second, connected=raw)
    assert error.value.code == "waiting_full"
    result = admission.prepare_admission_join(session.slug, second, connected=set())
    assert result.admission.permissions == "waiting"


def test_physical_full_keeps_admitted_request(context):
    session, _, keeper = context
    (user,) = add_users(session, 1)
    SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
    connected = {keeper.slug} | {f"occupant-{i}" for i in range(14)}
    with pytest.raises(admission.AdmissionError) as error:
        admission.prepare_admission_join(session.slug, user, connected=connected)
    assert error.value.code == "room_full"
    assert (
        AdmissionAttempt.objects.get(admission__session=session, admission__user=user).status == AttemptStatus.GRANTING
    )


def test_concurrent_approvals_compete_for_last_seat(context):
    session, room, keeper = context
    session.seats = 2
    session.save(update_fields=["seats"])
    attempts = [request(session, user) for user in add_users(session, 2)]
    barrier = Barrier(2)

    def worker(attempt):
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            try:
                return approve(room, keeper, attempt).status
            except admission.AdmissionError as error:
                return error.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, attempts))
    assert sorted(results) == ["admission_full", AttemptStatus.GRANTING]
    assert SessionAdmission.objects.filter(session=session, state=AdmissionState.ADMITTED).count() == 1
    assert AdmissionAttempt.objects.filter(admission__session=session, status=AttemptStatus.PENDING).count() == 1


def test_concurrent_waiting_tokens_never_exceed_five(context):
    session, _, _ = context
    users = add_users(session, 6)
    barrier = Barrier(6)

    def worker(user):
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            try:
                admission.prepare_admission_join(session.slug, user, connected=set())
                return "issued"
            except admission.AdmissionError as error:
                return error.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(worker, users))
    assert results.count("issued") == 5
    assert results.count("waiting_full") == 1
    assert AdmissionAttempt.objects.filter(admission__session=session, status=AttemptStatus.PENDING).count() == 6
    assert AdmissionAttempt.objects.filter(admission__session=session, token_expires_at__gt=timezone.now()).count() == 5
