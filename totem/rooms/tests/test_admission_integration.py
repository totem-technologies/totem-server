from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from totem.rooms import admission
from totem.rooms.livekit import LiveKitConfigurationError
from totem.rooms.models import AdmissionPermissionSync, AttemptStatus, Room
from totem.rooms.schemas import BanParticipantEvent, ErrorCode, TransitionError, UnbanParticipantEvent
from totem.rooms.state_machine import apply_event, record_join
from totem.rooms.tasks import _end_session, end_sessions_without_keeper
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


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


def revoke(room, keeper, user):
    durable = admission.get_admission(room.session.slug, user)
    room.refresh_from_db()
    return admission.revoke_admission(
        room.session.slug,
        keeper,
        user,
        expected_version=durable.version,
        expected_room_version=room.state_version,
    )


@pytest.mark.parametrize("enforced", [False, True])
def test_keeper_can_record_join_without_admission(settings, setup_room, enforced):
    settings.SERVER_ENFORCED_ADMISSION = enforced
    session, room, keeper, _ = setup_room
    original_order = room.talking_order.copy()
    if enforced:
        with pytest.raises(TransitionError) as error:
            record_join(session, keeper)
        assert error.value.code == ErrorCode.NOT_JOINABLE
    else:
        record_join(session, keeper)
    room.refresh_from_db()
    assert session.joined.filter(pk=keeper.pk).exists() is not enforced
    if enforced:
        assert room.talking_order == original_order
    else:
        assert keeper.slug in room.talking_order


def test_record_join_flag_off_preserves_legacy_join(settings, setup_room):
    settings.SERVER_ENFORCED_ADMISSION = False
    session, room, _, user = setup_room
    record_join(session, user)
    room.refresh_from_db()
    assert session.joined.filter(pk=user.pk).exists()
    assert user.slug in room.talking_order
    assert admission.get_admission(session.slug, user) is None


def test_record_join_requires_admission_without_mutating_join_or_order(settings, setup_room):
    settings.SERVER_ENFORCED_ADMISSION = True
    session, room, _, user = setup_room
    original_order = room.talking_order.copy()
    with pytest.raises(TransitionError) as error:
        record_join(session, user)
    assert error.value.code == ErrorCode.NOT_JOINABLE
    room.refresh_from_db()
    assert not session.joined.filter(pk=user.pk).exists()
    assert room.talking_order == original_order


def test_record_join_admitted_succeeds_but_revoked_cannot_rejoin(settings, setup_room):
    settings.SERVER_ENFORCED_ADMISSION = True
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


def test_remove_flag_off_skips_admission_removal(settings, client_with_user):
    settings.SERVER_ENFORCED_ADMISSION = False
    client, keeper = client_with_user
    user = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    decide(room, keeper, request(session, user))
    with (
        patch("totem.rooms.admission.record_removal") as record_removal,
        patch("totem.rooms.api.remove_participant") as remove,
    ):
        response = client.post(f"/api/mobile/protected/rooms/{session.slug}/remove/{user.slug}")
    assert response.status_code == 200
    record_removal.assert_not_called()
    remove.assert_called_once()
    assert admission.get_admission(session.slug, user).state == "admitted"


def test_remove_revokes_before_livekit_failure(settings, client_with_user):
    settings.SERVER_ENFORCED_ADMISSION = True
    client, keeper = client_with_user
    user = UserFactory()
    session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
    session.attendees.add(keeper, user)
    room = Room.objects.get_or_create_for_session(session)
    decide(room, keeper, request(session, user))

    def fail_livekit(*args, **kwargs):
        assert admission.get_admission(session.slug, user).state == "revoked"
        raise LiveKitConfigurationError("unavailable")

    with patch("totem.rooms.api.remove_participant", side_effect=fail_livekit) as remove:
        response = client.post(f"/api/mobile/protected/rooms/{session.slug}/remove/{user.slug}")
    assert response.status_code == 500
    remove.assert_called_once()
    assert admission.get_admission(session.slug, user).state == "revoked"
    assert not admission.is_authorized_to_enter(session.slug, user)


def test_ban_revokes_admission_and_unban_does_not_restore(settings, setup_room):
    settings.SERVER_ENFORCED_ADMISSION = True
    session, room, keeper, user = setup_room
    attempt = decide(room, keeper, request(session, user))
    room.refresh_from_db()
    state = apply_event(
        session.slug,
        keeper.slug,
        BanParticipantEvent(participant_slug=user.slug),
        room.state_version,
        {keeper.slug, user.slug},
    )
    attempt.refresh_from_db()
    assert attempt.status == "revoked"
    assert admission.get_admission(session.slug, user).state == "revoked"
    assert not admission.is_authorized_to_enter(session.slug, user)
    apply_event(
        session.slug, keeper.slug, UnbanParticipantEvent(participant_slug=user.slug), state.version, {keeper.slug}
    )
    room.refresh_from_db()
    assert user.slug not in room.banned_participants
    assert admission.get_admission(session.slug, user).state == "revoked"
    assert not admission.is_authorized_to_enter(session.slug, user)


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
        patch("totem.rooms.tasks.get_connected_participants", return_value=connected),
        patch("totem.rooms.tasks.publish_state"),
    ):
        count = end_sessions_without_keeper()
    session.refresh_from_db()
    assert count == (0 if current_keeper_connected else 1)
    assert (session.ended_at is None) == current_keeper_connected


def test_permanent_decline_survives_temporary_keeper_role(setup_room):
    session, room, keeper, user = setup_room
    decide(room, keeper, request(session, user), "permanently_decline")
    assert admission.get_admission(session.slug, user).state == "permanently_declined"
    room.keeper = user.slug
    room.save(update_fields=["keeper"])
    attempt = request(session, user)
    assert attempt.status == "granting"
    assert admission.get_admission(session.slug, user).state == "permanently_declined"
    room.keeper = keeper.slug
    room.save(update_fields=["keeper"])
    assert not admission.is_authorized_to_enter(session.slug, user)
    with pytest.raises(admission.AdmissionError) as error:
        request(session, user)
    assert error.value.code == "not_eligible"
    assert admission.get_admission(session.slug, user).state == "permanently_declined"


def test_expired_decision_persists_expiration_immediately(setup_room):
    session, room, keeper, user = setup_room
    attempt = request(session, user)
    attempt.expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=["expires_at"])
    with pytest.raises(admission.AdmissionError):
        decide(room, keeper, attempt)
    attempt.refresh_from_db()
    assert attempt.status == "expired"
    assert admission.get_admission(session.slug, user).state == "none"


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
    with pytest.raises(admission.AdmissionError) as error:
        admission.complete_admission(
            session.slug, user, attempt.request_id, attempt.attempt_id, expected_version=attempt.version
        )
    assert error.value.code == "not_eligible"
    attempt.refresh_from_db()
    assert attempt.status == "granting"
    assert not admission.is_authorized_to_enter(session.slug, user)
