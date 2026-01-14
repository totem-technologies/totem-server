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
        self.unpublished_circle = SpaceFactory(title="Unpublished Space", published=False)
        days = 1

        # Published circle events
        self.future_event = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.future_event2 = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.past_event = SessionFactory(
            space=self.space,
            start=timezone.now() - timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.cancelled_event = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 2)),
            cancelled=True,
            open=True,
        )
        self.closed_event = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=False,
        )
        self.unlisted_event = SessionFactory(
            space=self.space,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
            listed=False,
        )

        # Unpublished circle events
        self.unpublished_event = SessionFactory(
            space=self.unpublished_circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.unlisted__unpublished_event = SessionFactory(
            space=self.unpublished_circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )

    def test_other_sessions_in_space_unauth(self):
        events = other_sessions_in_space(None, self.future_event)
        self.assertNotIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertNotIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)

        events = other_sessions_in_space(None, self.unpublished_event)
        assert len(events) == 0

    def test_other_sessions_in_space_user(self):
        events = other_sessions_in_space(self.user, self.future_event)
        self.assertNotIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertNotIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)

        self.closed_event.attendees.add(self.user)
        self.unlisted_event.add_attendee(self.user)

        events = other_sessions_in_space(self.user, self.future_event)
        self.assertNotIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertIn(self.closed_event, events)
        self.assertIn(self.unlisted_event, events)

        events = other_sessions_in_space(self.user, self.unpublished_event)
        assert len(events) == 0

    def test_all_upcoming_recommended_sessions_unauth(self):
        events = all_upcoming_recommended_sessions(None)
        self.assertIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)
        self.assertNotIn(self.unpublished_event, events)
        self.assertNotIn(self.unlisted__unpublished_event, events)

    def test_all_upcoming_recommended_sessions_user(self):
        self.future_event.attendees.add(self.user)
        self.future_event2.attendees.add(self.user)
        events = all_upcoming_recommended_sessions(self.user)
        self.assertIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)
        self.assertNotIn(self.unpublished_event, events)
        self.assertNotIn(self.unlisted__unpublished_event, events)

    def test_all_upcoming_recommended_sessions_staff(self):
        self.future_event.attendees.add(self.staff_user)
        self.future_event2.attendees.add(self.staff_user)
        events = all_upcoming_recommended_sessions(self.staff_user)
        self.assertIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)
        self.assertIn(self.unpublished_event, events)
        self.assertIn(self.unlisted__unpublished_event, events)

    def test_recommended_full_event(self):
        users = [UserFactory() for _ in range(self.future_event.seats)]
        for user in users:
            self.future_event.add_attendee(user)
        events = all_upcoming_recommended_sessions(None)
        self.assertNotIn(self.future_event, events)
        self.assertIn(self.future_event2, events)

    def test_events_by_month(self):
        events = sessions_by_month(None, self.space.slug, self.future_event.start.month, self.future_event.start.year)
        self.assertIn(self.future_event, events)
        events = sessions_by_month(
            None, self.space.slug, self.cancelled_event.start.month, self.cancelled_event.start.year
        )
        self.assertNotIn(self.cancelled_event, events)
        self.cancelled_event.attendees.add(self.user)
        events = sessions_by_month(
            self.user, self.space.slug, self.cancelled_event.start.month, self.cancelled_event.start.year
        )
        self.assertNotIn(self.cancelled_event, events)
        self.assertNotIn(self.closed_event, events)
        self.closed_event.attendees.add(self.user)
        events = sessions_by_month(
            self.user, self.space.slug, self.closed_event.start.month, self.closed_event.start.year
        )
        self.assertIn(self.closed_event, events)
