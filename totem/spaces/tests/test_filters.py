from django.test import TestCase
from django.utils import timezone

from totem.rooms.models import Room
from totem.spaces.filters import (
    all_upcoming_recommended_sessions,
    get_upcoming_spaces_list,
    other_sessions_in_space,
    sessions_by_month,
    upcoming_attending_sessions,
    upcoming_sessions_by_author,
)
from totem.spaces.models import Session
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


def _ban_user(session: Session, user: User) -> None:
    room = Room.objects.get_or_create_for_session(session)
    room.banned_participants = [user.slug]
    room.save()


class TestFilters(TestCase):
    def setUp(self):
        self.user = UserFactory(name="testuser", is_staff=False)
        self.staff_user = UserFactory(name="staffuser", is_staff=True)
        self.space = SpaceFactory(title="Test Space", published=True)
        self.unpublished_space = SpaceFactory(title="Unpublished Space", published=False)
        days = 1

        # Published space sessions
        self.future_session = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.future_session2 = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.past_session = SessionFactory(
            space=self.space,
            start=timezone.now() - timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.cancelled_session = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 2)),
            cancelled=True,
            open=True,
        )
        self.closed_session = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=False,
        )
        self.unlisted_session = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
            listed=False,
        )

        self.in_progress_session = SessionFactory(
            space=self.space,
            start=timezone.now() - timezone.timedelta(minutes=30),
            duration_minutes=60,
            cancelled=False,
            open=True,
        )
        self.ended_early_session = SessionFactory(
            space=self.space,
            start=timezone.now() - timezone.timedelta(minutes=30),
            duration_minutes=60,
            cancelled=False,
            open=True,
            ended_at=timezone.now() - timezone.timedelta(minutes=5),
        )

        # Unpublished space sessions
        self.unpublished_session = SessionFactory(
            space=self.unpublished_space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.unlisted_unpublished_session = SessionFactory(
            space=self.unpublished_space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )

    def test_other_sessions_in_space_unauth(self):
        sessions = other_sessions_in_space(None, self.future_session)
        self.assertNotIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.cancelled_session, sessions)
        self.assertNotIn(self.closed_session, sessions)
        self.assertNotIn(self.unlisted_session, sessions)

        sessions = other_sessions_in_space(None, self.unpublished_session)
        assert len(sessions) == 0

    def test_other_sessions_in_space_user(self):
        sessions = other_sessions_in_space(self.user, self.future_session)
        self.assertNotIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.cancelled_session, sessions)
        self.assertNotIn(self.closed_session, sessions)
        self.assertNotIn(self.unlisted_session, sessions)

        self.closed_session.attendees.add(self.user)
        self.unlisted_session.add_attendee(self.user)

        sessions = other_sessions_in_space(self.user, self.future_session)
        self.assertNotIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.cancelled_session, sessions)
        self.assertIn(self.closed_session, sessions)
        self.assertIn(self.unlisted_session, sessions)

        sessions = other_sessions_in_space(self.user, self.unpublished_session)
        assert len(sessions) == 0

    def test_all_upcoming_recommended_sessions_unauth(self):
        sessions = all_upcoming_recommended_sessions(None)
        self.assertIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.cancelled_session, sessions)
        self.assertIn(self.closed_session, sessions)
        self.assertNotIn(self.unlisted_session, sessions)
        self.assertNotIn(self.unpublished_session, sessions)
        self.assertNotIn(self.unlisted_unpublished_session, sessions)

    def test_all_upcoming_recommended_sessions_user(self):
        self.future_session.attendees.add(self.user)
        self.future_session2.attendees.add(self.user)
        sessions = all_upcoming_recommended_sessions(self.user)
        self.assertIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.cancelled_session, sessions)
        self.assertIn(self.closed_session, sessions)
        self.assertNotIn(self.unlisted_session, sessions)
        self.assertNotIn(self.unpublished_session, sessions)
        self.assertNotIn(self.unlisted_unpublished_session, sessions)

    def test_all_upcoming_recommended_sessions_attendee_sees_unlisted(self):
        # Unlisted sessions stay hidden from browsers, but people attending
        # them can still find them anywhere sessions are shown.
        self.unlisted_session.add_attendee(self.user)
        sessions = all_upcoming_recommended_sessions(self.user)
        self.assertIn(self.unlisted_session, sessions)
        sessions = all_upcoming_recommended_sessions(None)
        self.assertNotIn(self.unlisted_session, sessions)

    def test_all_upcoming_recommended_sessions_staff(self):
        self.future_session.attendees.add(self.staff_user)
        self.future_session2.attendees.add(self.staff_user)
        sessions = all_upcoming_recommended_sessions(self.staff_user)
        self.assertIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.cancelled_session, sessions)
        self.assertIn(self.closed_session, sessions)
        self.assertNotIn(self.unlisted_session, sessions)
        self.assertIn(self.unpublished_session, sessions)
        self.assertIn(self.unlisted_unpublished_session, sessions)

    def test_recommended_full_session(self):
        # Full sessions stay listed; the detail page shows there are no seats left.
        users = [UserFactory() for _ in range(self.future_session.seats)]
        for user in users:
            self.future_session.add_attendee(user)
        sessions = all_upcoming_recommended_sessions(None)
        self.assertIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)

    def test_recommended_sessions_visible_until_ended(self):
        # In-progress sessions stay listed so attendees can find them; ended ones drop off.
        sessions = all_upcoming_recommended_sessions(None)
        self.assertIn(self.in_progress_session, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.ended_early_session, sessions)

    def _upcoming_for_space(self, user, space):
        match = next((s for s in get_upcoming_spaces_list(user) if s.slug == space.slug), None)
        return match.upcoming_sessions if match else []  # type: ignore[attr-defined]

    def test_spaces_list_sessions_visible_until_ended(self):
        sessions = self._upcoming_for_space(None, self.space)
        self.assertIn(self.in_progress_session, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.ended_early_session, sessions)

    def test_spaces_list_ordered_by_next_visible_session(self):
        # The unlisted session starts first but must not affect ordering.
        other_space = SpaceFactory(published=True)
        SessionFactory(space=other_space, start=self.unlisted_session.start + timezone.timedelta(hours=1))
        slugs = [s.slug for s in get_upcoming_spaces_list(None)]
        self.assertEqual(slugs.index(self.space.slug), 0)
        self.assertIn(other_space.slug, slugs)

    def test_spaces_list_includes_max_length_in_progress_session(self):
        # A max-length (2 hour) session that's mid-flight keeps its space listed.
        space = SpaceFactory(published=True)
        in_progress = SessionFactory(
            space=space,
            start=timezone.now() - timezone.timedelta(minutes=90),
            duration_minutes=120,
        )
        sessions = self._upcoming_for_space(None, space)
        self.assertIn(in_progress, sessions)

    def test_spaces_list_ties_break_deterministically(self):
        # Sessions start on the hour, so same-instant next sessions are
        # common. The paginated list must order ties the same way on every
        # request, or a space can be duplicated or skipped across pages.
        start = timezone.now() + timezone.timedelta(days=20)
        tied = [SpaceFactory(published=True) for _ in range(5)]
        for space in tied:
            SessionFactory(space=space, start=start)
        result = [s.slug for s in get_upcoming_spaces_list(None) if s.slug in {t.slug for t in tied}]
        self.assertEqual(result, sorted(t.slug for t in tied))

    def test_spaces_list_staff_sees_unpublished(self):
        slugs = [s.slug for s in get_upcoming_spaces_list(self.staff_user)]
        self.assertIn(self.unpublished_space.slug, slugs)
        slugs = [s.slug for s in get_upcoming_spaces_list(self.user)]
        self.assertNotIn(self.unpublished_space.slug, slugs)

    def test_livekit_sessions_listed_through_overruns(self):
        from totem.spaces.models import Space

        livekit_space = SpaceFactory(published=True)
        livekit_space.meeting_provider = Space.MeetingProviderChoices.LIVEKIT
        livekit_space.save()
        overrunning = SessionFactory(
            space=livekit_space,
            start=timezone.now() - timezone.timedelta(hours=2),
            duration_minutes=60,
            cancelled=False,
            open=True,
        )
        sessions = all_upcoming_recommended_sessions(None)
        self.assertIn(overrunning, sessions)
        self.assertEqual(livekit_space.next_session(), overrunning)

        overrunning.ended_at = timezone.now()
        overrunning.save()
        sessions = all_upcoming_recommended_sessions(None)
        self.assertNotIn(overrunning, sessions)

    def test_author_sessions_visible_until_ended(self):
        sessions = upcoming_sessions_by_author(self.user, self.space.author)
        self.assertIn(self.in_progress_session, sessions)
        self.assertNotIn(self.past_session, sessions)
        self.assertNotIn(self.ended_early_session, sessions)

    def test_session_detail_schema_lifecycle_times(self):
        from totem.spaces.filters import session_detail_schema

        schema = session_detail_schema(self.future_session, self.user)
        start = self.future_session.start
        self.assertEqual(schema.join_opens_at, start - timezone.timedelta(minutes=15))
        self.assertEqual(schema.join_closes_at, start + timezone.timedelta(minutes=10))
        self.assertEqual(schema.ends_at, start + timezone.timedelta(minutes=self.future_session.duration_minutes))

    def test_session_detail_schema_next_session(self):
        from totem.spaces.filters import session_detail_schema

        # An in-progress session points people to the space's next session.
        schema = session_detail_schema(self.in_progress_session, self.user)
        assert schema.next_session is not None
        self.assertEqual(schema.next_session.slug, self.future_session.slug)
        self.assertEqual(schema.next_session.link, self.future_session.get_absolute_url())

        # Same for an ended one.
        schema = session_detail_schema(self.past_session, self.user)
        assert schema.next_session is not None
        self.assertEqual(schema.next_session.slug, self.future_session.slug)

        # And a full one.
        users = [UserFactory() for _ in range(self.future_session.seats)]
        self.future_session.attendees.add(*users)
        schema = session_detail_schema(self.future_session, self.user)
        assert schema.next_session is not None
        self.assertEqual(schema.next_session.slug, self.future_session2.slug)

        # An upcoming session with open seats doesn't need one.
        schema = session_detail_schema(self.future_session2, self.user)
        self.assertIsNone(schema.next_session)

    def test_sessions_by_month(self):
        sessions = sessions_by_month(
            None, self.space.slug, self.future_session.start.month, self.future_session.start.year
        )
        self.assertIn(self.future_session, sessions)
        sessions = sessions_by_month(
            None, self.space.slug, self.cancelled_session.start.month, self.cancelled_session.start.year
        )
        self.assertNotIn(self.cancelled_session, sessions)
        self.cancelled_session.attendees.add(self.user)
        sessions = sessions_by_month(
            self.user, self.space.slug, self.cancelled_session.start.month, self.cancelled_session.start.year
        )
        self.assertNotIn(self.cancelled_session, sessions)
        self.assertNotIn(self.closed_session, sessions)
        self.closed_session.attendees.add(self.user)
        sessions = sessions_by_month(
            self.user, self.space.slug, self.closed_session.start.month, self.closed_session.start.year
        )
        self.assertIn(self.closed_session, sessions)

    def test_other_sessions_in_space_excludes_banned(self):
        _ban_user(self.future_session2, self.user)
        sessions = other_sessions_in_space(self.user, self.future_session)
        self.assertNotIn(self.future_session2, sessions)

    def test_sessions_by_month_excludes_banned(self):
        _ban_user(self.future_session, self.user)
        start = self.future_session.start
        sessions = sessions_by_month(self.user, self.space.slug, start.month, start.year)
        self.assertNotIn(self.future_session, sessions)
        # Other users are unaffected
        sessions = sessions_by_month(None, self.space.slug, start.month, start.year)
        self.assertIn(self.future_session, sessions)

    def test_all_upcoming_recommended_sessions_excludes_banned(self):
        _ban_user(self.future_session, self.user)
        sessions = all_upcoming_recommended_sessions(self.user)
        self.assertNotIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)

    def test_get_upcoming_spaces_list_excludes_banned(self):
        _ban_user(self.future_session, self.user)
        sessions = self._upcoming_for_space(self.user, self.space)
        self.assertNotIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)

    def test_upcoming_attending_sessions_excludes_banned(self):
        self.future_session.attendees.add(self.user)
        self.future_session2.attendees.add(self.user)
        _ban_user(self.future_session2, self.user)
        sessions = upcoming_attending_sessions(self.user)
        self.assertIn(self.future_session, sessions)
        self.assertNotIn(self.future_session2, sessions)

    def test_upcoming_sessions_by_author_excludes_banned(self):
        _ban_user(self.future_session, self.user)
        sessions = upcoming_sessions_by_author(self.user, self.space.author)
        self.assertNotIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)
