import datetime

import pytest
from django.utils import timezone

from totem.rooms.models import Room
from totem.users.tests.factories import UserFactory

from ..participants import participant_insights
from .factories import SessionFactory

pytestmark = pytest.mark.django_db


def past_session(**kwargs):
    return SessionFactory(start=timezone.now() - datetime.timedelta(days=7), **kwargs)


class TestParticipantInsights:
    def test_lists_attendees_with_name_and_email(self):
        session = SessionFactory()
        user = UserFactory(name="Claire")
        session.attendees.add(user)

        (insight,) = participant_insights(session)

        assert insight.name == "Claire"
        assert insight.email == user.email
        assert insight.slug == user.slug

    def test_counts_past_rsvps_and_attendance(self):
        session = SessionFactory()
        user = UserFactory()
        session.attendees.add(user)
        for _ in range(4):
            past = past_session()
            past.attendees.add(user)
        attended = past_session()
        attended.attendees.add(user)
        attended.joined.add(user)

        (insight,) = participant_insights(session)

        assert insight.rsvps == 5
        assert insight.attended == 1
        assert insight.attendance_percent == 20

    def test_upcoming_sessions_do_not_count_as_rsvps(self):
        session = SessionFactory()
        user = UserFactory()
        session.attendees.add(user)
        upcoming = SessionFactory(start=timezone.now() + datetime.timedelta(days=1))
        upcoming.attendees.add(user)

        (insight,) = participant_insights(session)

        assert insight.rsvps == 0
        assert insight.attendance_percent == 0

    def test_cancelled_sessions_are_not_held_against_anyone(self):
        session = SessionFactory()
        user = UserFactory()
        session.attendees.add(user)
        cancelled = past_session(cancelled=True)
        cancelled.attendees.add(user)
        attended = past_session()
        attended.attendees.add(user)
        attended.joined.add(user)

        (insight,) = participant_insights(session)

        assert insight.rsvps == 1
        assert insight.attendance_percent == 100

    def test_the_session_being_viewed_is_not_part_of_its_own_history(self):
        session = past_session()
        user = UserFactory()
        session.attendees.add(user)
        session.joined.add(user)

        (insight,) = participant_insights(session)

        assert insight.rsvps == 0
        assert insight.attended == 0
        assert insight.first_time is True
        assert insight.joined_this_session is True

    def test_joining_without_an_rsvp_still_counts_as_a_signup(self):
        # attendees and joined are independent, so someone can be removed from
        # attendees after the fact. Never report more attended than RSVPed.
        session = SessionFactory()
        user = UserFactory()
        session.attendees.add(user)
        past = past_session()
        past.joined.add(user)

        (insight,) = participant_insights(session)

        assert insight.attended == 1
        assert insight.rsvps == 1
        assert insight.attendance_percent == 100

    def test_first_time_when_never_attended(self):
        session = SessionFactory()
        newcomer = UserFactory()
        regular = UserFactory()
        session.attendees.add(newcomer, regular)
        # A no-show RSVP does not make someone a returning participant.
        no_show = past_session()
        no_show.attendees.add(newcomer)
        attended = past_session()
        attended.attendees.add(regular)
        attended.joined.add(regular)

        insights = {i.slug: i for i in participant_insights(session)}

        assert insights[newcomer.slug].first_time is True
        assert insights[regular.slug].first_time is False

    def test_banned_from_another_space(self):
        session = SessionFactory()
        banned_user = UserFactory()
        other_user = UserFactory()
        session.attendees.add(banned_user, other_user)
        other_session = past_session()
        Room.objects.create(
            session=other_session,
            keeper=other_session.space.author.slug,
            banned_participants=[banned_user.slug],
        )

        insights = {i.slug: i for i in participant_insights(session)}

        assert insights[banned_user.slug].banned is True
        assert insights[other_user.slug].banned is False

    def test_joined_this_session(self):
        session = past_session()
        joiner = UserFactory()
        absent = UserFactory()
        session.attendees.add(joiner, absent)
        session.joined.add(joiner)

        insights = {i.slug: i for i in participant_insights(session)}

        assert insights[joiner.slug].joined_this_session is True
        assert insights[absent.slug].joined_this_session is False

    def test_no_attendees(self):
        assert participant_insights(SessionFactory()) == []
