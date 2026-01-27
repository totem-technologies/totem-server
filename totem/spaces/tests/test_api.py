from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from totem.spaces.api import EventCalendarFilterSchema, SessionsFilterSchema
from totem.spaces.tests.factories import SessionFactory, SpaceCategoryFactory, SpaceFactory
from totem.users.tests.factories import KeeperProfileFactory, UserFactory


class TestSessionListAPI:
    def test_get_session_list_bad_category(self, client, db):
        response = client.get(
            reverse("api-1:events_list"), SessionsFilterSchema(category="empty", author=""), format="json"
        )
        assert response.status_code == 200
        assert response.json() == {"count": 0, "items": []}

    def test_get_session_list(self, client, db):
        session = SessionFactory()
        session.save()
        response = client.get(reverse("api-1:events_list"), SessionsFilterSchema(category="", author=""), format="json")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_session_list_filters_category(self, client, db):
        category = SpaceCategoryFactory()
        space = SpaceFactory(categories=[category])
        session = SessionFactory(space=space)
        session.save()
        session2 = SessionFactory()
        session2.save()
        response = client.get(
            reverse("api-1:events_list"),
            SessionsFilterSchema(category=category.slug, author=""),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_session_list_filters_author(self, client, db):
        space = SpaceFactory()
        session = SessionFactory(space=space)
        session.save()
        session2 = SessionFactory()
        session2.save()
        response = client.get(
            reverse("api-1:events_list"),
            SessionsFilterSchema(category="", author=space.author.slug),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_session_list_limit(self, client, db):
        session = SessionFactory()
        session.save()
        session2 = SessionFactory()
        session2.save()
        response = client.get(
            reverse("api-1:events_list"),
            SessionsFilterSchema(category="", author=""),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2
        response = client.get(
            reverse("api-1:events_list"),
            SessionsFilterSchema(category="", author="").model_dump() | {"limit": 1},
            format="json",
        )
        print(response.wsgi_request)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1


class TestFilterOptions:
    def test_get_filter_options(self, client, db):
        # past sessions should not be included
        past_session = SessionFactory(start=timezone.now() - timedelta(days=1))
        past_session.save()
        category = SpaceCategoryFactory()
        space = SpaceFactory(categories=[category])
        session = SessionFactory(space=space)
        session.save()
        session2 = SessionFactory()
        session2.save()
        response = client.get(reverse("api-1:events_filter_options"), format="json")
        assert response.status_code == 200
        assert len(response.json()["categories"]) == 1
        assert len(response.json()["authors"]) == 2
        assert response.json()["categories"][0]["slug"] == category.slug
        assert response.json()["categories"][0]["name"] == category.name
        slugs = [response.json()["authors"][0]["slug"], response.json()["authors"][1]["slug"]]
        assert space.author.slug in slugs
        assert session2.space.author.slug in slugs
        names = [response.json()["authors"][0]["name"], response.json()["authors"][1]["name"]]
        assert space.author.name in names
        assert session2.space.author.name in names


class TestSessionDetail:
    def test_session_detail(self, client, db):
        session = SessionFactory()
        url = reverse("api-1:event_detail", kwargs={"event_slug": session.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["slug"] == session.slug

    def test_session_detail_not_found(self, client, db):
        url = reverse("api-1:event_detail", kwargs={"event_slug": "not-found"})
        response = client.get(url)
        assert response.status_code == 404

    def test_session_detail_authenticated(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        session = SessionFactory()
        url = reverse("api-1:event_detail", kwargs={"event_slug": session.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["slug"] == session.slug
        assert response.json()["attending"] is False

    def test_session_detail_authenticated_attending(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        session = SessionFactory()
        session.attendees.add(user)
        url = reverse("api-1:event_detail", kwargs={"event_slug": session.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["slug"] == session.slug
        assert response.json()["attending"] is True

    def test_session_detail_ended(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        now_minus_one = timezone.now() - timedelta(days=1)
        session = SessionFactory(start=now_minus_one)
        session.attendees.add(user)
        url = reverse("api-1:event_detail", kwargs={"event_slug": session.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["ended"] is True
        assert response.json()["attending"] is True


class TestSessionCalendar:
    def test_session_calendar_future(self, client, db):
        now_plus_week = timezone.now() + timedelta(days=7)
        session = SessionFactory(start=now_plus_week)
        url = reverse("api-1:event_calendar")
        response = client.get(
            url,
            EventCalendarFilterSchema(
                space_slug=session.space.slug, month=now_plus_week.month, year=now_plus_week.year
            ).model_dump(),
        )
        assert response.status_code == 200
        assert response.json()[0]["title"] == session.title

    def test_session_calendar_now(self, client, db):
        now = timezone.now()
        session = SessionFactory(start=now)
        SessionFactory(start=now, cancelled=True)
        url = reverse("api-1:event_calendar")
        response = client.get(
            url,
            EventCalendarFilterSchema(space_slug=session.space.slug, month=now.month, year=now.year).model_dump(),
        )
        assert response.status_code == 200
        assert response.json()[0]["title"] == session.title
        assert len(response.json()) == 1


class TestWebflowSessionsAPI:
    def test_webflow_no_sessions(self, client, db):
        response = client.get(reverse("api-1:webflow_events_list"))
        assert response.status_code == 200
        assert response.json() == []

    def test_webflow_sessions_ordered(self, client, db):
        now = timezone.now()
        keeper1 = UserFactory()
        KeeperProfileFactory(user=keeper1, username="keeper1")
        space1 = SpaceFactory(author=keeper1)
        session1 = SessionFactory(space=space1, start=now + timedelta(days=2))

        keeper2 = UserFactory()
        KeeperProfileFactory(user=keeper2, username="keeper2")
        space2 = SpaceFactory(author=keeper2)
        session2 = SessionFactory(space=space2, start=now + timedelta(days=1))

        response = client.get(reverse("api-1:webflow_events_list"))

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["start"] == session2.start.isoformat()
        assert data[1]["start"] == session1.start.isoformat()

    def test_webflow_filter_keeper(self, client, db):
        # Create keepers with profiles
        keeper1 = UserFactory()
        KeeperProfileFactory(user=keeper1, username="keeper1")
        space1 = SpaceFactory(author=keeper1)
        SessionFactory(space=space1)

        keeper2 = UserFactory()
        KeeperProfileFactory(user=keeper2, username="keeper2")
        space2 = SpaceFactory(author=keeper2)
        SessionFactory(space=space2)

        # Test filter
        response = client.get(reverse("api-1:webflow_events_list"), {"keeper_username": "keeper1"})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["keeper_username"] == "keeper1"

    def test_webflow_past_sessions_excluded(self, client, db):
        SessionFactory(start=timezone.now() - timedelta(days=1))
        response = client.get(reverse("api-1:webflow_events_list"))
        assert len(response.json()) == 0


class TestListSpaces:
    def test_list_spaces(self, client, db):
        session = SessionFactory()
        session.save()
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["slug"] == session.space.slug

    def test_list_spaces_no_sessions(self, client, db):
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert response.json() == []

    def test_list_spaces_multiple_sessions(self, client, db):
        session1 = SessionFactory()
        session1.save()
        session2 = SessionFactory()
        session2.save()
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_spaces_with_category(self, client, db):
        category = SpaceCategoryFactory()
        space = SpaceFactory(categories=[category])
        session = SessionFactory(space=space)
        session.save()
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert response.json()[0]["category"] == category.name

    def test_list_spaces_with_full_sessions(self, client, db):
        """Test that spaces with full sessions still appear in the spaces list.

        Note: This test is expected to FAIL with the current implementation,
        demonstrating that spaces with only full sessions don't appear in listings.
        """
        # Create a space with a full session
        space = SpaceFactory()
        session = SessionFactory(space=space, seats=1)
        user = UserFactory()
        session.attendees.add(user)  # This makes the session full (1 seat, 1 attendee)

        # Create another space with a non-full session
        space2 = SpaceFactory()
        SessionFactory(space=space2)

        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200

        # Extract slugs from the response
        data = response.json()
        slugs = [s["slug"] for s in data]

        # This assertion will fail - demonstrating that spaces with only full sessions
        # don't currently appear in the listing
        assert space.slug in slugs, "Spaces with full sessions should still appear in listings"
        assert space2.slug in slugs
        assert len(slugs) == 2  # Both spaces should be in the response

    def test_list_spaces_with_seats_left(self, client, db):
        """Test that spaces in the list API show correct seats_left values."""
        now = timezone.now()

        # Create three spaces with sessions having different seat availability
        # Space 1: All seats available (10 seats, 0 attendees)
        space1 = SpaceFactory(title="All Seats Available")
        SessionFactory(space=space1, seats=10, start=now + timedelta(days=1))

        # Space 2: Some seats taken (10 seats, 3 attendees = 7 seats left)
        space2 = SpaceFactory(title="Some Seats Taken")
        session2 = SessionFactory(space=space2, seats=10, start=now + timedelta(days=2))
        # Add 3 attendees
        for _ in range(3):
            user = UserFactory()
            session2.attendees.add(user)

        # Space 3: Full session (3 seats, 3 attendees = 0 seats left)
        space3 = SpaceFactory(title="Full Session")
        session3 = SessionFactory(space=space3, seats=3, start=now + timedelta(days=3))
        # Add 3 attendees (making it full)
        for _ in range(3):
            user = UserFactory()
            session3.attendees.add(user)

        # Call the API
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200

        data = response.json()

        # Verify we have all three spaces
        assert len(data) == 3, "Expected 3 spaces, including the one with full session"

        # Create a mapping of title to space data for easier testing
        title_to_space = {item["title"]: item for item in data}

        # Verify each space has the correct seats_left value
        assert title_to_space["All Seats Available"]["next_event"]["seats_left"] == 10, (
            "Expected 10 seats left for 'All Seats Available'"
        )
        assert title_to_space["Some Seats Taken"]["next_event"]["seats_left"] == 7, (
            "Expected 7 seats left for 'Some Seats Taken'"
        )
        assert title_to_space["Full Session"]["next_event"]["seats_left"] == 0, (
            "Expected 0 seats left for 'Full Session'"
        )
        # Verify other properties are present
        for space in data:
            assert "slug" in space
            assert "title" in space
            assert "author" in space
            assert "next_event" in space
            assert "start" in space["next_event"]
            assert "link" in space["next_event"]
            assert "seats_left" in space["next_event"]
