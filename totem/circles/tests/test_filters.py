from django.test import TestCase
from django.utils import timezone

from totem.circles.filters import (
    all_upcoming_recommended_events,
    other_events_in_circle,
)
from totem.circles.tests.factories import CircleEventFactory, CircleFactory
from totem.users.tests.factories import UserFactory


class TestFilters(TestCase):
    def setUp(self):
        self.user = UserFactory(name="testuser", is_staff=False)
        self.staff_user = UserFactory(name="staffuser", is_staff=True)
        self.circle = CircleFactory(title="Test Circle", published=True)
        self.unpublished_circle = CircleFactory(title="Unpublished Circle", published=False)
        days = 1

        # Published circle events
        self.future_event = CircleEventFactory(
            circle=self.circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.future_event2 = CircleEventFactory(
            circle=self.circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.past_event = CircleEventFactory(
            circle=self.circle,
            start=timezone.now() - timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.cancelled_event = CircleEventFactory(
            circle=self.circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=True,
            open=True,
        )
        self.closed_event = CircleEventFactory(
            circle=self.circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=False,
        )
        self.unlisted_event = CircleEventFactory(
            circle=self.circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
            listed=False,
        )

        # Unpublished circle events
        self.unpublished_event = CircleEventFactory(
            circle=self.unpublished_circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )
        self.unlisted__unpublished_event = CircleEventFactory(
            circle=self.unpublished_circle,
            start=timezone.now() + timezone.timedelta(days=(days := days + 1)),
            cancelled=False,
            open=True,
        )

    def test_other_events_in_circle_unauth(self):
        events = other_events_in_circle(None, self.future_event)
        self.assertNotIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertNotIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)

        events = other_events_in_circle(None, self.unpublished_event)
        assert len(events) == 0

    def test_other_events_in_circle_user(self):
        events = other_events_in_circle(self.user, self.future_event)
        self.assertNotIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertNotIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)

        self.closed_event.attendees.add(self.user)
        self.unlisted_event.add_attendee(self.user)

        events = other_events_in_circle(self.user, self.future_event)
        self.assertNotIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertIn(self.closed_event, events)
        self.assertIn(self.unlisted_event, events)

        events = other_events_in_circle(self.user, self.unpublished_event)
        assert len(events) == 0

    def test_all_upcoming_recommended_events_unauth(self):
        events = all_upcoming_recommended_events(None)
        self.assertIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertNotIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)
        self.assertNotIn(self.unpublished_event, events)
        self.assertNotIn(self.unlisted__unpublished_event, events)

    def test_all_upcoming_recommended_events_user(self):
        self.future_event.attendees.add(self.user)
        self.future_event2.attendees.add(self.user)
        events = all_upcoming_recommended_events(self.user)
        self.assertNotIn(self.future_event, events)
        self.assertNotIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertNotIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)
        self.assertNotIn(self.unpublished_event, events)
        self.assertNotIn(self.unlisted__unpublished_event, events)

    def test_all_upcoming_recommended_events_staff(self):
        self.future_event.attendees.add(self.staff_user)
        self.future_event2.attendees.add(self.staff_user)
        events = all_upcoming_recommended_events(self.staff_user)
        self.assertNotIn(self.future_event, events)
        self.assertNotIn(self.future_event2, events)
        self.assertNotIn(self.past_event, events)
        self.assertNotIn(self.cancelled_event, events)
        self.assertNotIn(self.closed_event, events)
        self.assertNotIn(self.unlisted_event, events)
        self.assertIn(self.unpublished_event, events)
        self.assertIn(self.unlisted__unpublished_event, events)

    def test_recommended_full_event(self):
        users = [UserFactory() for _ in range(self.future_event.seats)]
        for user in users:
            self.future_event.add_attendee(user)
        events = all_upcoming_recommended_events(None)
        self.assertNotIn(self.future_event, events)
        self.assertIn(self.future_event2, events)
