from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from totem.rooms.admission import AdmissionError, request_admission
from totem.rooms.models import AdmissionAttempt, AdmissionState, AttemptStatus, Room, SessionAdmission
from totem.rooms.schemas import RoomStatus
from totem.spaces.actions import JoinSessionAction
from totem.spaces.filters import join_listing_queryset
from totem.spaces.models import Session, Space
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory


@pytest.fixture
def entry(db):
    session = SessionFactory(
        start=timezone.now() - timedelta(minutes=30), space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT
    )
    user = UserFactory()
    session.attendees.add(user)
    room = Room.objects.get_or_create_for_session(session)
    return session, room, user


def test_current_keeper_and_admitted_attendee_have_returning_window(entry):
    session, room, user = entry
    keeper = UserFactory()
    session.attendees.add(keeper)
    room.keeper = keeper.slug
    room.save(update_fields=["keeper"])
    SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
    assert session.space.author != keeper
    assert session.can_join(keeper)
    assert session.can_join(user)
    session.ended_at = timezone.now()
    assert not session.can_join(keeper)
    assert not session.can_join(user)


@pytest.mark.parametrize("state", [AdmissionState.NONE, AdmissionState.REVOKED])
def test_legacy_join_does_not_extend_unadmitted_window(entry, state):
    session, _, user = entry
    session.joined.add(user)
    SessionAdmission.objects.create(session=session, user=user, state=state)
    assert not session.can_join(user)


@pytest.mark.parametrize("status", [AttemptStatus.PENDING, AttemptStatus.GRANTING])
def test_existing_attempt_continues_until_expiry(entry, status):
    session, _, user = entry
    admission = SessionAdmission.objects.create(session=session, user=user)
    attempt = AdmissionAttempt.objects.create(
        admission=admission,
        request_id=uuid4(),
        attempt_id=uuid4(),
        status=status,
        expires_at=timezone.now() + timedelta(minutes=1),
    )
    assert session.can_join(user)
    attempt.expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=["expires_at"])
    assert not session.can_join(user)


def test_prefetched_attempt_expiry_and_other_user_isolation(entry):
    session, room, user = entry
    admission = SessionAdmission.objects.create(session=session, user=user)
    attempt = AdmissionAttempt.objects.create(
        admission=admission,
        request_id=uuid4(),
        attempt_id=uuid4(),
        status=AttemptStatus.PENDING,
        expires_at=timezone.now() + timedelta(minutes=1),
    )
    listed = join_listing_queryset(Session.objects.filter(pk=session.pk), user).get()
    assert listed.can_join(user)
    other = UserFactory()
    session.attendees.add(other)
    assert not listed.join_window(other)[1] == attempt.expires_at
    with patch("django.utils.timezone.now", return_value=attempt.expires_at + timedelta(seconds=1)):
        assert not listed.can_join(user)


def test_can_join_fetches_livekit_state_once_per_call(entry):
    original, room, user = entry
    session = Session.objects.select_related("space__author").get(pk=original.pk)
    session.start = timezone.now() - timedelta(minutes=1)
    admission = SessionAdmission.objects.create(session=session, user=user)
    with CaptureQueriesContext(connection) as queries:
        assert session.can_join(user)
    selects = [query["sql"] for query in queries if query["sql"].startswith("SELECT")]
    assert sum('FROM "rooms_room"' in sql for sql in selects) == 1
    assert sum('FROM "rooms_sessionadmission"' in sql for sql in selects) == 1
    room.banned_participants = [user.slug]
    room.save(update_fields=["banned_participants"])
    assert not session.can_join(user)
    room.banned_participants = []
    room.save(update_fields=["banned_participants"])
    assert session.can_join(user)
    admission.state = AdmissionState.PERMANENTLY_DECLINED
    admission.save(update_fields=["state"])
    assert not session.can_join(user)


def test_pending_continuation_does_not_authorize_a_new_request(entry):
    session, _, user = entry
    admission = SessionAdmission.objects.create(session=session, user=user)
    AdmissionAttempt.objects.create(
        admission=admission,
        request_id=uuid4(),
        attempt_id=uuid4(),
        status=AttemptStatus.PENDING,
        expires_at=timezone.now() + timedelta(minutes=1),
    )
    assert session.can_join(user)
    with pytest.raises(AdmissionError) as error:
        request_admission(session.slug, user, uuid4(), uuid4())
    assert error.value.code == "not_eligible"


@pytest.mark.parametrize(
    ("provider", "joinable"),
    [
        (Space.MeetingProviderChoices.LIVEKIT, False),
        (Space.MeetingProviderChoices.GOOGLE_MEET, True),
    ],
)
def test_inactive_user_joinability(entry, provider, joinable):
    session, _, user = entry
    session.space.meeting_provider = provider
    session.start = timezone.now() - timedelta(minutes=1)
    user.is_active = False
    assert session.can_join(user) is joinable


@pytest.mark.parametrize(
    ("provider", "joinable"),
    [
        (Space.MeetingProviderChoices.LIVEKIT, False),
        (Space.MeetingProviderChoices.GOOGLE_MEET, True),
    ],
)
def test_ended_room_joinability_before_session_end_sync(entry, provider, joinable):
    session, room, user = entry
    session.space.meeting_provider = provider
    session.start = timezone.now() - timedelta(minutes=1)
    room.status = RoomStatus.ENDED
    room.save(update_fields=["status"])
    assert session.ended_at is None
    assert session.can_join(user) is joinable


def test_keeper_still_requires_rsvp(entry):
    session, room, user = entry
    room.keeper = user.slug
    room.save(update_fields=["keeper"])
    session.attendees.remove(user)
    assert not session.can_join(user)


def test_bans_and_declines_deny_but_keeper_bypasses_decline(entry):
    session, room, user = entry
    SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.PERMANENTLY_DECLINED)
    assert not session.can_join(user)
    room.keeper = user.slug
    room.save(update_fields=["keeper"])
    assert session.can_join(user)
    room.banned_participants = [user.slug]
    room.save(update_fields=["banned_participants"])
    assert not session.can_join(user)


@pytest.mark.parametrize("signed", [False, True])
def test_livekit_browser_redirect_does_not_record_attendance(entry, client, signed):
    session, _, user = entry
    SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
    if signed:
        url = JoinSessionAction(user=user, parameters={"session_slug": session.slug}).build_url()
    else:
        client.force_login(user)
        url = reverse("spaces:join", kwargs={"session_slug": session.slug})
    with patch("totem.spaces.views.analytics.event_joined") as analytics:
        response = client.get(url)
    assert response.url == session.room_url()
    assert not session.joined.filter(pk=user.pk).exists()
    analytics.assert_not_called()


def test_signed_link_obeys_decline(entry, client):
    session, _, user = entry
    SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.PERMANENTLY_DECLINED)
    url = JoinSessionAction(user=user, parameters={"session_slug": session.slug}).build_url()
    response = client.get(url)
    assert response.url != session.room_url()
    assert not session.joined.filter(pk=user.pk).exists()


def test_google_meet_browser_records_redirect(entry, client):
    session, _, user = entry
    session.space.meeting_provider = Space.MeetingProviderChoices.GOOGLE_MEET
    session.space.save(update_fields=["meeting_provider"])
    session.start = timezone.now() - timedelta(minutes=1)
    session.save(update_fields=["start"])
    client.force_login(user)
    with patch("totem.spaces.views.analytics.event_joined") as analytics:
        response = client.get(reverse("spaces:join", kwargs={"session_slug": session.slug}))
    assert response.url == session.room_url()
    assert session.joined.filter(pk=user.pk).exists()
    analytics.assert_called_once()
