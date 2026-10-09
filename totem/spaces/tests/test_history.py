import datetime

import pytest
from django.utils import timezone

from totem.rooms.models import Room
from totem.users.tests.factories import UserFactory

from ..history import SessionStatus, session_history
from ..models import SessionFeedback, SessionFeedbackOptions
from .factories import SessionFactory, SpaceFactory

pytestmark = pytest.mark.django_db


def past_session(days_ago: int = 7, **kwargs):
    return SessionFactory(start=timezone.now() - datetime.timedelta(days=days_ago), **kwargs)


def future_session(**kwargs):
    return SessionFactory(start=timezone.now() + datetime.timedelta(days=1), **kwargs)


class TestSessionHistory:
    def test_lists_sessions_signed_up_for_or_joined_newest_first(self):
        user = UserFactory()
        older = past_session(days_ago=14)
        older.attendees.add(user)
        newer = past_session(days_ago=7)
        newer.joined.add(user)
        upcoming = future_session()
        upcoming.attendees.add(user)
        past_session().attendees.add(UserFactory())

        history = session_history(user)

        assert [entry.session.pk for entry in history.entries] == [upcoming.pk, newer.pk, older.pk]

    def test_status_of_each_session(self):
        user = UserFactory()
        attended = past_session()
        attended.attendees.add(user)
        attended.joined.add(user)
        no_show = past_session()
        no_show.attendees.add(user)
        cancelled = past_session(cancelled=True)
        cancelled.attendees.add(user)
        upcoming = future_session()
        upcoming.attendees.add(user)

        statuses = {entry.session.pk: entry.status for entry in session_history(user).entries}

        assert statuses == {
            attended.pk: SessionStatus.ATTENDED,
            no_show.pk: SessionStatus.NO_SHOW,
            cancelled.pk: SessionStatus.CANCELLED,
            upcoming.pk: SessionStatus.UPCOMING,
        }

    def test_in_progress_session_is_not_a_no_show(self):
        user = UserFactory()
        session = SessionFactory(start=timezone.now() - datetime.timedelta(minutes=10), duration_minutes=60)
        session.attendees.add(user)

        history = session_history(user)

        assert history.entries[0].status == SessionStatus.IN_PROGRESS
        assert history.no_shows == 0

    def test_joined_without_rsvp(self):
        # Someone can be dropped from attendees after joining.
        user = UserFactory()
        session = past_session()
        session.joined.add(user)

        (entry,) = session_history(user).entries

        assert entry.signed_up is False
        assert entry.status == SessionStatus.ATTENDED

    def test_banned_from_session(self):
        user = UserFactory()
        banned_from = past_session()
        banned_from.attendees.add(user)
        Room.objects.create(session=banned_from, keeper=banned_from.space.author.slug, banned_participants=[user.slug])
        fine = past_session()
        fine.attendees.add(user)
        Room.objects.create(session=fine, keeper=fine.space.author.slug)

        banned = {entry.session.pk: entry.banned for entry in session_history(user).entries}

        assert banned == {banned_from.pk: True, fine.pk: False}

    def test_feedback_left(self):
        user = UserFactory()
        session = past_session()
        session.attendees.add(user)
        session.joined.add(user)
        SessionFeedback.objects.create(
            session=session, user=user, feedback=SessionFeedbackOptions.DOWN, message="Too noisy"
        )
        other = past_session()
        other.attendees.add(user)

        feedback = {entry.session.pk: entry.feedback for entry in session_history(user).entries}

        assert feedback[other.pk] is None
        assert feedback[session.pk] is not None
        assert feedback[session.pk].feedback == SessionFeedbackOptions.DOWN
        assert feedback[session.pk].message == "Too noisy"

    def test_totals_by_keeper(self):
        user = UserFactory()
        keeper_a = UserFactory(name="Ana")
        keeper_b = UserFactory(name="Ben")
        space_a = SpaceFactory(author=keeper_a)
        space_b = SpaceFactory(author=keeper_b)
        for _ in range(2):
            session = past_session(space=space_a)
            session.attendees.add(user)
            session.joined.add(user)
        no_show = past_session(space=space_a)
        no_show.attendees.add(user)
        past_session(space=space_a, cancelled=True).attendees.add(user)
        future_session(space=space_a).attendees.add(user)
        past_session(space=space_b).attendees.add(user)

        keepers = {k.keeper.pk: k for k in session_history(user).keepers}

        assert keepers[keeper_a.pk].attended == 2
        assert keepers[keeper_a.pk].no_shows == 1
        assert keepers[keeper_a.pk].cancelled == 1
        assert keepers[keeper_a.pk].upcoming == 1
        assert keepers[keeper_b.pk].attended == 0
        assert keepers[keeper_b.pk].no_shows == 1
        # Most sessions first.
        assert [k.keeper.pk for k in session_history(user).keepers] == [keeper_a.pk, keeper_b.pk]

    def test_overall_totals(self):
        user = UserFactory()
        attended = past_session()
        attended.attendees.add(user)
        attended.joined.add(user)
        past_session().attendees.add(user)
        past_session().attendees.add(user)

        history = session_history(user)

        assert history.attended == 1
        assert history.no_shows == 2
        assert history.attendance_percent == 33

    def test_no_sessions(self):
        history = session_history(UserFactory())
        assert history.entries == []
        assert history.keepers == []
        assert history.attendance_percent == 0
