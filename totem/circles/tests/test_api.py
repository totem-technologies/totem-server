from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from totem.circles.api import EventCalendarFilterSchema, EventsFilterSchema
from totem.circles.tests.factories import CircleCategoryFactory, CircleEventFactory, CircleFactory
from totem.users.tests.factories import KeeperProfileFactory, UserFactory


class TestCircleListAPI:
    def test_get_circle_list_bad_category(self, client, db):
        response = client.get(
            reverse("api-1:events_list"), EventsFilterSchema(category="empty", author=""), format="json"
        )
        assert response.status_code == 200
        assert response.json() == {"count": 0, "items": []}

    def test_get_circle_list(self, client, db):
        event = CircleEventFactory()
        event.save()
        response = client.get(reverse("api-1:events_list"), EventsFilterSchema(category="", author=""), format="json")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_circle_list_filters_category(self, client, db):
        category = CircleCategoryFactory()
        circle = CircleFactory(categories=[category])
        event = CircleEventFactory(circle=circle)
        event.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(
            reverse("api-1:events_list"),
            EventsFilterSchema(category=category.slug, author=""),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_circle_list_filters_author(self, client, db):
        circle = CircleFactory()
        event = CircleEventFactory(circle=circle)
        event.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(
            reverse("api-1:events_list"),
            EventsFilterSchema(category="", author=circle.author.slug),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_circle_list_limit(self, client, db):
        event = CircleEventFactory()
        event.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(
            reverse("api-1:events_list"),
            EventsFilterSchema(category="", author=""),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2
        response = client.get(
            reverse("api-1:events_list"),
            EventsFilterSchema(category="", author="").model_dump() | {"limit": 1},
            format="json",
        )
        print(response.wsgi_request)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1


class TestFilterOptions:
    def test_get_filter_options(self, client, db):
        # past events should not be included
        past_event = CircleEventFactory(start=timezone.now() - timedelta(days=1))
        past_event.save()
        category = CircleCategoryFactory()
        circle = CircleFactory(categories=[category])
        event = CircleEventFactory(circle=circle)
        event.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(reverse("api-1:events_filter_options"), format="json")
        assert response.status_code == 200
        assert len(response.json()["categories"]) == 1
        assert len(response.json()["authors"]) == 2
        assert response.json()["categories"][0]["slug"] == category.slug
        assert response.json()["categories"][0]["name"] == category.name
        slugs = [response.json()["authors"][0]["slug"], response.json()["authors"][1]["slug"]]
        assert circle.author.slug in slugs
        assert event2.circle.author.slug in slugs
        names = [response.json()["authors"][0]["name"], response.json()["authors"][1]["name"]]
        assert circle.author.name in names
        assert event2.circle.author.name in names


class TestEventDetail:
    def test_event_detail(self, client, db):
        event = CircleEventFactory()
        url = reverse("api-1:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["slug"] == event.slug

    def test_event_detail_not_found(self, client, db):
        url = reverse("api-1:event_detail", kwargs={"event_slug": "not-found"})
        response = client.get(url)
        assert response.status_code == 404

    def test_event_detail_authenticated(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        event = CircleEventFactory()
        url = reverse("api-1:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["slug"] == event.slug
        assert response.json()["attending"] is False

    def test_event_detail_authenticated_attending(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        event = CircleEventFactory()
        event.attendees.add(user)
        url = reverse("api-1:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["slug"] == event.slug
        assert response.json()["attending"] is True

    def test_event_detail_ended(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        now_minus_one = timezone.now() - timedelta(days=1)
        event = CircleEventFactory(start=now_minus_one)
        event.attendees.add(user)
        url = reverse("api-1:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["ended"] is True
        assert response.json()["attending"] is True


class TestEventCalendar:
    def test_event_calendar_future(self, client, db):
        now_plus_week = timezone.now() + timedelta(days=7)
        event = CircleEventFactory(start=now_plus_week)
        url = reverse("api-1:event_calendar")
        response = client.get(
            url,
            EventCalendarFilterSchema(
                space_slug=event.circle.slug, month=now_plus_week.month, year=now_plus_week.year
            ).model_dump(),
        )
        assert response.status_code == 200
        assert response.json()[0]["title"] == event.title

    def test_event_calendar_now(self, client, db):
        now = timezone.now()
        event = CircleEventFactory(start=now)
        CircleEventFactory(start=now, cancelled=True)
        url = reverse("api-1:event_calendar")
        response = client.get(
            url,
            EventCalendarFilterSchema(space_slug=event.circle.slug, month=now.month, year=now.year).model_dump(),
        )
        assert response.status_code == 200
        assert response.json()[0]["title"] == event.title
        assert len(response.json()) == 1


class TestWebflowEventsAPI:
    def test_webflow_no_events(self, client, db):
        response = client.get(reverse("api-1:webflow_events_list"))
        assert response.status_code == 200
        assert response.json() == []

    def test_webflow_events_ordered(self, client, db):
        now = timezone.now()
        keeper1 = UserFactory()
        KeeperProfileFactory(user=keeper1, username="keeper1")
        circle1 = CircleFactory(author=keeper1)
        event1 = CircleEventFactory(circle=circle1, start=now + timedelta(days=2))

        keeper2 = UserFactory()
        KeeperProfileFactory(user=keeper2, username="keeper2")
        circle2 = CircleFactory(author=keeper2)
        event2 = CircleEventFactory(circle=circle2, start=now + timedelta(days=1))

        response = client.get(reverse("api-1:webflow_events_list"))

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["start"] == event2.start.isoformat()
        assert data[1]["start"] == event1.start.isoformat()

    def test_webflow_filter_keeper(self, client, db):
        # Create keepers with profiles
        keeper1 = UserFactory()
        KeeperProfileFactory(user=keeper1, username="keeper1")
        circle1 = CircleFactory(author=keeper1)
        CircleEventFactory(circle=circle1)

        keeper2 = UserFactory()
        KeeperProfileFactory(user=keeper2, username="keeper2")
        circle2 = CircleFactory(author=keeper2)
        CircleEventFactory(circle=circle2)

        # Test filter
        response = client.get(reverse("api-1:webflow_events_list"), {"keeper_username": "keeper1"})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["keeper_username"] == "keeper1"

    def test_webflow_past_events_excluded(self, client, db):
        CircleEventFactory(start=timezone.now() - timedelta(days=1))
        response = client.get(reverse("api-1:webflow_events_list"))
        assert len(response.json()) == 0


class TestListSpaces:
    def test_list_spaces(self, client, db):
        event = CircleEventFactory()
        event.save()
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["slug"] == event.circle.slug

    def test_list_spaces_no_events(self, client, db):
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert response.json() == []

    def test_list_spaces_multiple_events(self, client, db):
        event1 = CircleEventFactory()
        event1.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_spaces_with_category(self, client, db):
        category = CircleCategoryFactory()
        circle = CircleFactory(categories=[category])
        event = CircleEventFactory(circle=circle)
        event.save()
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert response.json()[0]["category"] == category.name

    def test_list_spaces_with_full_events(self, client, db):
        """Test that spaces with full events still appear in the spaces list.

        Note: This test is expected to FAIL with the current implementation,
        demonstrating that spaces with only full events don't appear in listings.
        """
        # Create a space with a full event
        circle = CircleFactory()
        event = CircleEventFactory(circle=circle, seats=1)
        user = UserFactory()
        event.attendees.add(user)  # This makes the event full (1 seat, 1 attendee)

        # Create another space with a non-full event
        circle2 = CircleFactory()
        CircleEventFactory(circle=circle2)

        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200

        # Extract slugs from the response
        data = response.json()
        slugs = [space["slug"] for space in data]

        # This assertion will fail - demonstrating that spaces with only full events
        # don't currently appear in the listing
        assert circle.slug in slugs, "Spaces with full events should still appear in listings"
        assert circle2.slug in slugs
        assert len(slugs) == 2  # Both spaces should be in the response

    def test_list_spaces_with_seats_left(self, client, db):
        """Test that spaces in the list API show correct seats_left values."""
        now = timezone.now()

        # Create three spaces with events having different seat availability
        # Space 1: All seats available (10 seats, 0 attendees)
        circle1 = CircleFactory(title="All Seats Available")
        CircleEventFactory(circle=circle1, seats=10, start=now + timedelta(days=1))

        # Space 2: Some seats taken (10 seats, 3 attendees = 7 seats left)
        circle2 = CircleFactory(title="Some Seats Taken")
        event2 = CircleEventFactory(circle=circle2, seats=10, start=now + timedelta(days=2))
        # Add 3 attendees
        for _ in range(3):
            user = UserFactory()
            event2.attendees.add(user)

        # Space 3: Full event (3 seats, 3 attendees = 0 seats left)
        circle3 = CircleFactory(title="Full Event")
        event3 = CircleEventFactory(circle=circle3, seats=3, start=now + timedelta(days=3))
        # Add 3 attendees (making it full)
        for _ in range(3):
            user = UserFactory()
            event3.attendees.add(user)

        # Call the API
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200

        data = response.json()

        # Verify we have all three spaces
        assert len(data) == 3, "Expected 3 spaces, including the one with full event"

        # Create a mapping of title to space data for easier testing
        title_to_space = {item["title"]: item for item in data}

        # Verify each space has the correct seats_left value
        assert (
            title_to_space["All Seats Available"]["nextEvent"]["seats_left"] == 10
        ), "Expected 10 seats left for 'All Seats Available'"
        assert (
            title_to_space["Some Seats Taken"]["nextEvent"]["seats_left"] == 7
        ), "Expected 7 seats left for 'Some Seats Taken'"
        # Verify other properties are present
        for space in data:
            assert "slug" in space
            assert "title" in space
            assert "author" in space
            assert "nextEvent" in space
            assert "start" in space["nextEvent"]
            assert "link" in space["nextEvent"]
            assert "seats_left" in space["nextEvent"]
