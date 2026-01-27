from django.test import TestCase
from django.utils import timezone

from totem.spaces.filters import (
    all_upcoming_recommended_sessions,
    other_sessions_in_space,
    sessions_by_month,
)
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.tests.factories import UserFactory


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
        users = [UserFactory() for _ in range(self.future_session.seats)]
        for user in users:
            self.future_session.add_attendee(user)
        sessions = all_upcoming_recommended_sessions(None)
        self.assertNotIn(self.future_session, sessions)
        self.assertIn(self.future_session2, sessions)

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
