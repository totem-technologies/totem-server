import datetime

import pytest
from django.utils import timezone

from totem.spaces.mobile_api.mobile_filters import (
    get_upcoming_spaces_list,
    get_user_upcoming_sessions,
    next_session_schema,
    session_detail_schema,
    space_detail_schema,
    upcoming_recommended_sessions,
    upcoming_recommended_spaces,
)
from totem.spaces.tests.factories import SessionFactory, SpaceCategoryFactory, SpaceFactory
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestGetUserUpcomingSessions:
    """Tests for the get_user_upcoming_sessions function."""

    def test_returns_sessions_user_is_attending(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
        )
        session.attendees.add(user)

        result = list(get_user_upcoming_sessions(user))

        assert len(result) == 1
        assert result[0] == session

    def test_excludes_sessions_user_not_attending(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
        )

        result = list(get_user_upcoming_sessions(user))

        assert len(result) == 0

    def test_excludes_cancelled_sessions(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=True,
        )
        session.attendees.add(user)

        result = list(get_user_upcoming_sessions(user))

        assert len(result) == 0

    def test_excludes_ended_sessions(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        # Session that started 2 hours ago with 60 min duration (ended 1 hour ago)
        session = SessionFactory(
            space=space,
            start=timezone.now() - datetime.timedelta(hours=2),
            duration_minutes=60,
            cancelled=False,
        )
        session.attendees.add(user)

        result = list(get_user_upcoming_sessions(user))

        assert len(result) == 0

    def test_includes_in_progress_sessions(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        # Session that started 30 mins ago with 60 min duration (30 mins left)
        session = SessionFactory(
            space=space,
            start=timezone.now() - datetime.timedelta(minutes=30),
            duration_minutes=60,
            cancelled=False,
        )
        session.attendees.add(user)

        result = list(get_user_upcoming_sessions(user))

        assert len(result) == 1
        assert result[0] == session

    def test_excludes_unpublished_space_sessions_by_default(self):
        user = UserFactory()
        space = SpaceFactory(published=False)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
        )
        session.attendees.add(user)

        result = list(get_user_upcoming_sessions(user))

        assert len(result) == 0

    def test_includes_unpublished_space_sessions_when_require_published_false(self):
        user = UserFactory()
        space = SpaceFactory(published=False)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
        )
        session.attendees.add(user)

        result = list(get_user_upcoming_sessions(user, require_published=False))

        assert len(result) == 1
        assert result[0] == session

    def test_orders_by_start_time(self):
        user = UserFactory()
        space = SpaceFactory(published=True)

        session_later = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=3),
            cancelled=False,
        )
        session_sooner = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
        )
        session_later.attendees.add(user)
        session_sooner.attendees.add(user)

        result = list(get_user_upcoming_sessions(user))

        assert len(result) == 2
        assert result[0] == session_sooner
        assert result[1] == session_later

    def test_returns_empty_for_user_with_no_sessions(self):
        user = UserFactory()

        result = list(get_user_upcoming_sessions(user))

        assert len(result) == 0


@pytest.mark.django_db
class TestGetUpcomingSpacesList:
    """Tests for the get_upcoming_spaces_list function."""

    def test_returns_published_spaces_with_upcoming_sessions(self):
        space = SpaceFactory(published=True)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )

        result = list(get_upcoming_spaces_list())

        assert len(result) == 1
        assert result[0] == space

    def test_excludes_unpublished_spaces(self):
        space = SpaceFactory(published=False)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )

        result = list(get_upcoming_spaces_list())

        assert len(result) == 0

    def test_excludes_spaces_with_only_past_sessions(self):
        space = SpaceFactory(published=True)
        SessionFactory(
            space=space,
            start=timezone.now() - datetime.timedelta(hours=1),
        )

        result = list(get_upcoming_spaces_list())

        assert len(result) == 0

    def test_returns_distinct_spaces(self):
        space = SpaceFactory(published=True)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=2),
        )

        result = list(get_upcoming_spaces_list())

        assert len(result) == 1
        assert result[0] == space

    def test_prefetches_upcoming_sessions(self):
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )

        result = list(get_upcoming_spaces_list())

        assert hasattr(result[0], "upcoming_sessions")
        assert session in result[0].upcoming_sessions


@pytest.mark.django_db
class TestUpcomingRecommendedSpaces:
    """Tests for the upcoming_recommended_spaces function."""

    def test_returns_spaces_with_upcoming_sessions(self):
        space = SpaceFactory(published=True)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )

        result = list(upcoming_recommended_spaces(None))

        assert len(result) == 1
        assert result[0] == space

    def test_excludes_unpublished_for_regular_user(self):
        user = UserFactory(is_staff=False)
        space = SpaceFactory(published=False)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )

        result = list(upcoming_recommended_spaces(user))

        assert len(result) == 0

    def test_includes_unpublished_for_staff(self):
        staff = UserFactory(is_staff=True)
        space = SpaceFactory(published=False)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )

        result = list(upcoming_recommended_spaces(staff))

        assert len(result) == 1
        assert result[0] == space

    def test_filters_by_category_slug(self):
        category = SpaceCategoryFactory(slug="anxiety")
        space_with_category = SpaceFactory(published=True)
        space_with_category.categories.add(category)
        space_without_category = SpaceFactory(published=True)

        SessionFactory(space=space_with_category, start=timezone.now() + datetime.timedelta(hours=1))
        SessionFactory(space=space_without_category, start=timezone.now() + datetime.timedelta(hours=1))

        result = list(upcoming_recommended_spaces(None, categories=["anxiety"]))

        assert len(result) == 1
        assert result[0] == space_with_category

    def test_filters_by_category_name(self):
        category = SpaceCategoryFactory(name="Grief Support", slug="grief")
        space_with_category = SpaceFactory(published=True)
        space_with_category.categories.add(category)

        SessionFactory(space=space_with_category, start=timezone.now() + datetime.timedelta(hours=1))

        result = list(upcoming_recommended_spaces(None, categories=["Grief Support"]))

        assert len(result) == 1
        assert result[0] == space_with_category

    def test_filters_by_author(self):
        author = UserFactory(slug="jane-doe")
        space_by_author = SpaceFactory(published=True, author=author)
        space_other = SpaceFactory(published=True)

        SessionFactory(space=space_by_author, start=timezone.now() + datetime.timedelta(hours=1))
        SessionFactory(space=space_other, start=timezone.now() + datetime.timedelta(hours=1))

        result = list(upcoming_recommended_spaces(None, author="jane-doe"))

        assert len(result) == 1
        assert result[0] == space_by_author


@pytest.mark.django_db
class TestUpcomingRecommendedSessions:
    """Tests for the upcoming_recommended_sessions function."""

    def test_returns_upcoming_sessions(self):
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=True,
        )

        result = list(upcoming_recommended_sessions(None))

        assert len(result) == 1
        assert result[0] == session

    def test_excludes_cancelled_sessions(self):
        space = SpaceFactory(published=True)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=True,
            listed=True,
        )

        result = list(upcoming_recommended_sessions(None))

        assert len(result) == 0

    def test_excludes_unlisted_sessions(self):
        space = SpaceFactory(published=True)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=False,
        )

        result = list(upcoming_recommended_sessions(None))

        assert len(result) == 0

    def test_excludes_full_sessions(self):
        space = SpaceFactory(published=True)
        user = UserFactory()
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=True,
            seats=1,
        )
        session.attendees.add(user)

        result = list(upcoming_recommended_sessions(None))

        assert len(result) == 0

    def test_excludes_unpublished_for_regular_user(self):
        user = UserFactory(is_staff=False)
        space = SpaceFactory(published=False)
        SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=True,
        )

        result = list(upcoming_recommended_sessions(user))

        assert len(result) == 0

    def test_includes_unpublished_for_staff(self):
        staff = UserFactory(is_staff=True)
        space = SpaceFactory(published=False)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=True,
        )

        result = list(upcoming_recommended_sessions(staff))

        assert len(result) == 1
        assert result[0] == session

    def test_filters_by_category(self):
        category = SpaceCategoryFactory(slug="depression")
        space = SpaceFactory(published=True)
        space.categories.add(category)
        other_space = SpaceFactory(published=True)

        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=True,
        )
        SessionFactory(
            space=other_space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=True,
        )

        result = list(upcoming_recommended_sessions(None, categories=["depression"]))

        assert len(result) == 1
        assert result[0] == session

    def test_filters_by_author(self):
        author = UserFactory(slug="john-smith")
        space = SpaceFactory(published=True, author=author)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=True,
        )

        result = list(upcoming_recommended_sessions(None, author="john-smith"))

        assert len(result) == 1
        assert result[0] == session

    def test_orders_by_start_time(self):
        space = SpaceFactory(published=True)
        later_session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=3),
            cancelled=False,
            listed=True,
        )
        sooner_session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
            listed=True,
        )

        result = list(upcoming_recommended_sessions(None))

        assert len(result) == 2
        assert result[0] == sooner_session
        assert result[1] == later_session


@pytest.mark.django_db
class TestSessionDetailSchema:
    """Tests for the session_detail_schema function."""

    def test_returns_correct_schema_fields(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
        )

        result = session_detail_schema(session, user)

        assert result.slug == session.slug
        assert result.title == session.title
        assert result.duration == session.duration_minutes
        assert result.start == session.start
        assert result.cancelled == session.cancelled

    def test_attending_true_when_user_is_attendee(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(space=space, start=timezone.now() + datetime.timedelta(hours=1))
        session.attendees.add(user)

        result = session_detail_schema(session, user)

        assert result.attending is True

    def test_attending_false_when_user_not_attendee(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(space=space, start=timezone.now() + datetime.timedelta(hours=1))

        result = session_detail_schema(session, user)

        assert result.attending is False

    def test_subscribed_true_when_user_subscribed(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        space.subscribed.add(user)
        session = SessionFactory(space=space, start=timezone.now() + datetime.timedelta(hours=1))

        result = session_detail_schema(session, user)

        assert result.subscribed is True

    def test_subscribed_false_when_user_not_subscribed(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(space=space, start=timezone.now() + datetime.timedelta(hours=1))

        result = session_detail_schema(session, user)

        assert result.subscribed is False

    def test_ended_true_for_past_session(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() - datetime.timedelta(hours=2),
            duration_minutes=60,
        )

        result = session_detail_schema(session, user)

        assert result.ended is True

    def test_ended_false_for_future_session(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )

        result = session_detail_schema(session, user)

        assert result.ended is False


@pytest.mark.django_db
class TestNextSessionSchema:
    """Tests for the next_session_schema function."""

    def test_returns_correct_schema_fields(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            cancelled=False,
        )

        result = next_session_schema(session, user)

        assert result.slug == session.slug
        assert result.start == session.start
        assert result.title == session.title
        assert result.duration == session.duration_minutes
        assert result.cancelled == session.cancelled

    def test_attending_reflects_user_status(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(space=space, start=timezone.now() + datetime.timedelta(hours=1))

        result_not_attending = next_session_schema(session, user)
        assert result_not_attending.attending is False

        session.attendees.add(user)
        result_attending = next_session_schema(session, user)
        assert result_attending.attending is True

    def test_seats_left_calculation(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
            seats=5,
        )

        result = next_session_schema(session, user)
        assert result.seats_left == 5

        attendee = UserFactory()
        session.attendees.add(attendee)
        result = next_session_schema(session, user)
        assert result.seats_left == 4


@pytest.mark.django_db
class TestSpaceDetailSchema:
    """Tests for the space_detail_schema function."""

    def test_returns_correct_schema_fields(self):
        user = UserFactory()
        space = SpaceFactory(published=True)

        result = space_detail_schema(space, user)

        assert result.slug == space.slug
        assert result.title == space.title
        assert result.short_description == space.short_description
        assert result.price == space.price
        assert result.recurring == space.recurring

    def test_includes_category_name(self):
        user = UserFactory()
        category = SpaceCategoryFactory(name="Anxiety")
        space = SpaceFactory(published=True)
        space.categories.add(category)

        result = space_detail_schema(space, user)

        assert result.category == "Anxiety"

    def test_category_none_when_no_category(self):
        user = UserFactory()
        space = SpaceFactory(published=True)

        result = space_detail_schema(space, user)

        assert result.category is None

    def test_subscribers_count(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        subscriber1 = UserFactory()
        subscriber2 = UserFactory()
        space.subscribed.add(subscriber1, subscriber2)

        result = space_detail_schema(space, user)

        assert result.subscribers == 2

    def test_next_events_includes_upcoming_sessions(self):
        user = UserFactory()
        space = SpaceFactory(published=True)
        session = SessionFactory(
            space=space,
            start=timezone.now() + datetime.timedelta(hours=1),
        )

        result = space_detail_schema(space, user)

        assert len(result.next_events) == 1
        assert result.next_events[0].slug == session.slug

    def test_author_included(self):
        author = UserFactory(name="Test Author")
        user = UserFactory()
        space = SpaceFactory(published=True, author=author)

        result = space_detail_schema(space, user)

        assert result.author.name == "Test Author"
        assert result.author.slug == author.slug
