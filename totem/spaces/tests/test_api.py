from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from totem.spaces.api import EventCalendarFilterSchema, SessionsFilterSchema
from totem.spaces.tests.factories import SessionFactory, SpaceCategoryFactory, SpaceFactory
from totem.users.tests.factories import UserFactory


class TestSessionListAPI:
    def test_session_list_queries_do_not_grow_with_rows(self, client, db):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def query_count() -> int:
            with CaptureQueriesContext(connection) as ctx:
                response = client.get(
                    reverse("api-1:events_list"), SessionsFilterSchema(category="", author=""), format="json"
                )
            assert response.status_code == 200
            return len(ctx)

        for _ in range(2):
            SessionFactory(space=SpaceFactory(author=UserFactory()))
        small = query_count()
        for _ in range(8):
            SessionFactory(space=SpaceFactory(author=UserFactory()))
        assert query_count() == small

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

    def test_session_detail_unpublished_staff_only(self, client, db):
        # The JSON API must match the HTML page: drafts are staff-only.
        session = SessionFactory(space__published=False)
        url = reverse("api-1:event_detail", kwargs={"event_slug": session.slug})
        assert client.get(url).status_code == 404
        client.force_login(UserFactory())
        assert client.get(url).status_code == 404
        client.force_login(UserFactory(is_staff=True))
        assert client.get(url).status_code == 200

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


class TestRsvpConflictResolution:
    def test_requires_authentication(self, client, db):
        event = SessionFactory()

        response = client.post(
            reverse("api-1:rsvp_resolve_conflicts", kwargs={"event_slug": event.slug}),
            {"conflicting_session_slugs": []},
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_replaces_all_conflicting_sessions(self, client, db):
        start = timezone.now() + timedelta(days=1)
        event = SessionFactory(title="New Session", start=start, duration_minutes=60)
        first = SessionFactory(title="First Conflict", start=start, duration_minutes=60)
        second = SessionFactory(
            title="Second Conflict",
            start=start + timedelta(minutes=30),
            duration_minutes=60,
        )
        unrelated = SessionFactory(start=start + timedelta(hours=2), duration_minutes=60)
        user = UserFactory()
        first.attendees.add(user)
        second.attendees.add(user)
        unrelated.attendees.add(user)
        client.force_login(user)

        response = client.post(
            reverse("api-1:rsvp_resolve_conflicts", kwargs={"event_slug": event.slug}),
            {"conflicting_session_slugs": [first.slug, second.slug]},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["slug"] == event.slug
        assert response.json()["attending"] is True
        assert event.attendees.filter(pk=user.pk).exists()
        assert not first.attendees.filter(pk=user.pk).exists()
        assert not second.attendees.filter(pk=user.pk).exists()
        assert unrelated.attendees.filter(pk=user.pk).exists()

    def test_returns_fresh_conflicts_without_changing_attendance(self, client, db):
        start = timezone.now() + timedelta(days=1)
        event = SessionFactory(start=start, duration_minutes=60)
        submitted = SessionFactory(title="Submitted Conflict", start=start, duration_minutes=60)
        new_conflict = SessionFactory(
            title="New Conflict",
            start=start + timedelta(minutes=30),
            duration_minutes=60,
        )
        user = UserFactory()
        submitted.attendees.add(user)
        new_conflict.attendees.add(user)
        client.force_login(user)

        response = client.post(
            reverse("api-1:rsvp_resolve_conflicts", kwargs={"event_slug": event.slug}),
            {"conflicting_session_slugs": [submitted.slug]},
            content_type="application/json",
        )

        assert response.status_code == 409
        assert {session["slug"] for session in response.json()["conflicting_sessions"]} == {
            submitted.slug,
            new_conflict.slug,
        }
        assert submitted.attendees.filter(pk=user.pk).exists()
        assert new_conflict.attendees.filter(pk=user.pk).exists()
        assert not event.attendees.filter(pk=user.pk).exists()

    def test_returns_session_error_when_target_becomes_unavailable(self, client, db):
        start = timezone.now() + timedelta(days=1)
        event = SessionFactory(start=start, duration_minutes=60, seats=1)
        conflict = SessionFactory(start=start, duration_minutes=60)
        user = UserFactory()
        conflict.attendees.add(user)
        event.attendees.add(UserFactory())
        client.force_login(user)

        response = client.post(
            reverse("api-1:rsvp_resolve_conflicts", kwargs={"event_slug": event.slug}),
            {"conflicting_session_slugs": [conflict.slug]},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json() == {"detail": "There are no spots left"}
        assert conflict.attendees.filter(pk=user.pk).exists()
        assert not event.attendees.filter(pk=user.pk).exists()


class TestSpacesSummary:
    def test_summary_requires_login(self, client, db):
        response = client.get(reverse("api-1:spaces_summary"))
        assert response.status_code == 401

    def test_summary_sections(self, client, db):
        user = UserFactory()
        client.force_login(user)
        attending = SessionFactory()
        attending.attendees.add(user)
        other = SessionFactory()
        response = client.get(reverse("api-1:spaces_summary"))
        assert response.status_code == 200
        data = response.json()
        assert [s["slug"] for s in data["upcoming"]] == [attending.slug]
        assert data["upcoming"][0]["attending"] is True
        explore_slugs = [s["slug"] for s in data["explore"]]
        assert other.space.slug in explore_slugs
        explore_space = next(s for s in data["explore"] if s["slug"] == other.space.slug)
        assert explore_space["next_event"]["rsvp_url"] == reverse("spaces:rsvp", kwargs={"session_slug": other.slug})
        # spaces the user already has a session in are not re-suggested
        assert attending.space.slug not in explore_slugs
        assert attending.space.slug not in [s["slug"] for s in data["for_you"]]

    def test_summary_upcoming_space_image_link(self, client, db):
        user = UserFactory()
        client.force_login(user)
        no_image = SessionFactory()
        no_image.attendees.add(user)
        space = SpaceFactory()
        space.image = "space-images/test.jpg"
        space.save()
        with_image = SessionFactory(space=space)
        with_image.attendees.add(user)
        response = client.get(reverse("api-1:spaces_summary"))
        assert response.status_code == 200
        by_slug = {s["slug"]: s for s in response.json()["upcoming"]}
        # ninja's DjangoGetter serializes FieldFile as its url (or None when unset)
        assert by_slug[no_image.slug]["space"]["image"] is None
        link = by_slug[with_image.slug]["space"]["image"]
        assert link is not None
        assert link.endswith("space-images/test.jpg")
        assert link.startswith("/")

    def test_summary_excludes_ended_sessions(self, client, db):
        user = UserFactory()
        client.force_login(user)
        ended = SessionFactory(start=timezone.now() - timedelta(days=1))
        ended.attendees.add(user)
        response = client.get(reverse("api-1:spaces_summary"))
        assert response.status_code == 200
        assert response.json()["upcoming"] == []

    def test_summary_explore_ordered_by_soonest_session(self, client, db):
        user = UserFactory()
        client.force_login(user)
        later = SessionFactory(start=timezone.now() + timedelta(days=5))
        soon = SessionFactory(start=timezone.now() + timedelta(days=1))
        response = client.get(reverse("api-1:spaces_summary"))
        assert response.status_code == 200
        explore_slugs = [s["slug"] for s in response.json()["explore"]]
        assert explore_slugs == [soon.space.slug, later.space.slug]

    def test_summary_recommendations_are_capped(self, client, db):
        user = UserFactory()
        client.force_login(user)
        for _ in range(10):
            SessionFactory()
        response = client.get(reverse("api-1:spaces_summary"))
        assert response.status_code == 200
        assert len(response.json()["explore"]) == 8

    def test_summary_query_count_is_bounded(self, client, db, django_assert_max_num_queries):
        """Serializing recommendation spaces must use the queryset's prefetches,
        not per-space queries."""
        user = UserFactory()
        client.force_login(user)
        for _ in range(8):
            SessionFactory()
        with django_assert_max_num_queries(20):
            response = client.get(reverse("api-1:spaces_summary"))
        assert response.status_code == 200

    def test_summary_for_you_matches_subscribed_categories(self, client, db):
        user = UserFactory()
        client.force_login(user)
        category = SpaceCategoryFactory()
        subscribed_space = SpaceFactory(categories=[category])
        SessionFactory(space=subscribed_space)
        subscribed_space.subscribed.add(user)
        recommended_space = SpaceFactory(categories=[category])
        SessionFactory(space=recommended_space)
        unrelated_space = SpaceFactory()
        SessionFactory(space=unrelated_space)
        response = client.get(reverse("api-1:spaces_summary"))
        assert response.status_code == 200
        for_you_slugs = [s["slug"] for s in response.json()["for_you"]]
        assert recommended_space.slug in for_you_slugs
        assert unrelated_space.slug not in for_you_slugs


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

    def test_list_spaces_hides_unlisted_and_orders_consistently(self, client, db):
        # TOT-1238: a space's card must be positioned by the same session it
        # displays, and unlisted sessions must not surface publicly.
        now = timezone.now()
        space_a = SpaceFactory(title="Space A")
        SessionFactory(space=space_a, start=now + timedelta(hours=1), listed=False)
        SessionFactory(space=space_a, start=now + timedelta(hours=2), cancelled=True)
        a_listed = SessionFactory(space=space_a, start=now + timedelta(days=3))
        space_b = SpaceFactory(title="Space B")
        b_listed = SessionFactory(space=space_b, start=now + timedelta(days=1))

        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        data = response.json()
        assert [s["slug"] for s in data] == [space_b.slug, space_a.slug]
        by_slug = {s["slug"]: s for s in data}
        assert by_slug[space_a.slug]["next_event"]["slug"] == a_listed.slug
        assert by_slug[space_b.slug]["next_event"]["slug"] == b_listed.slug

    def test_list_spaces_only_unlisted_sessions_hides_space(self, client, db):
        space = SpaceFactory()
        SessionFactory(space=space, listed=False)
        response = client.get(reverse("api-1:spaces_list"))
        assert response.status_code == 200
        assert response.json() == []

    def test_list_spaces_unpublished_visible_to_staff_only(self, client, db):
        space = SpaceFactory(published=False)
        SessionFactory(space=space)
        response = client.get(reverse("api-1:spaces_list"))
        assert [s["slug"] for s in response.json()] == []

        client.force_login(UserFactory(is_staff=True))
        response = client.get(reverse("api-1:spaces_list"))
        assert [s["slug"] for s in response.json()] == [space.slug]

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
