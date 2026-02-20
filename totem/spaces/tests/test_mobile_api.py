from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.onboard.tests.factories import OnboardModelFactory
from totem.spaces.models import SessionFeedback, SessionFeedbackOptions
from totem.spaces.tests.factories import SessionFactory, SpaceCategoryFactory, SpaceFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestMobileApiSpaces:
    def test_subscribe_to_space(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        space = SpaceFactory(published=True)

        url = reverse("mobile-api:spaces_subscribe", kwargs={"space_slug": space.slug})
        response = client.post(url)

        assert response.status_code == 200
        assert response.json() is True
        assert space.subscribed.filter(pk=user.pk).exists()

    def test_subscribe_to_unpublished_space(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        space = SpaceFactory(published=False)

        url = reverse("mobile-api:spaces_subscribe", kwargs={"space_slug": space.slug})
        response = client.post(url)

        assert response.status_code == 404

    def test_unsubscribe_from_space(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        space = SpaceFactory(published=True)
        space.subscribed.add(user)

        url = reverse("mobile-api:spaces_unsubscribe", kwargs={"space_slug": space.slug})
        response = client.delete(url)

        assert response.status_code == 200
        assert response.json() is True
        assert not space.subscribed.filter(pk=user.pk).exists()

    def test_list_subscriptions(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        space1 = SpaceFactory(published=True)
        space2 = SpaceFactory(published=True)
        SpaceFactory(published=True)

        space1.subscribed.add(user)
        space2.subscribed.add(user)

        url = reverse("mobile-api:spaces_subscriptions")
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        slugs = {item["slug"] for item in data}
        assert space1.slug in slugs
        assert space2.slug in slugs

    def test_list_spaces(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        event = SessionFactory()
        event.save()

        url = reverse("mobile-api:mobile_spaces_list")
        response = client.get(url)

        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["slug"] == event.space.slug

    def test_list_spaces_author_with_legacy_timezone(self, client_with_user: tuple[Client, User]):
        """Ensure spaces serialize correctly when the author has a legacy timezone like America/Buenos_Aires."""
        client, _ = client_with_user
        author = UserFactory()
        User.objects.filter(pk=author.pk).update(timezone="America/Buenos_Aires")
        event = SessionFactory(space__author=author)
        event.save()

        url = reverse("mobile-api:mobile_spaces_list")
        response = client.get(url)

        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_list_spaces_no_events(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        response = client.get(reverse("mobile-api:mobile_spaces_list"))
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_get_session_detail(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        event = SessionFactory(space__published=True)
        space = event.space

        url = reverse("mobile-api:session_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == event.slug
        assert data["space"]["slug"] == space.slug

    def test_get_session_detail_unpublished_circle(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        event = SessionFactory(space__published=False)
        space = event.space

        url = reverse("mobile-api:session_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == event.slug
        assert data["space"]["slug"] == space.slug

    def test_get_space_detail(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        space = SpaceFactory(published=True)

        url = reverse("mobile-api:spaces_detail", kwargs={"space_slug": space.slug})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == space.slug
        assert data["title"] == space.title
        assert data["slug"] == space.slug

    def test_get_space_detail_unpublished(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        space = SpaceFactory(published=False)

        url = reverse("mobile-api:spaces_detail", kwargs={"space_slug": space.slug})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == space.slug

    def test_get_keeper_spaces(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        keeper1 = UserFactory(is_staff=True)
        space = SpaceFactory(author=keeper1, published=True)
        SessionFactory(space=space)

        # This space should not appear as it is unpublished
        unpublished_space = SpaceFactory(author=keeper1, published=False)
        SessionFactory(space=unpublished_space)

        url = reverse("mobile-api:keeper_spaces", kwargs={"slug": keeper1.slug})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["slug"] == space.slug

    def test_get_keeper_spaces_no_spaces(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        keeper = UserFactory(is_staff=True)

        url = reverse("mobile-api:keeper_spaces", kwargs={"slug": keeper.slug})
        response = client.get(url)

        assert response.status_code == 200
        assert response.json() == []

    def test_get_keeper_spaces_nonexistent(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        url = reverse("mobile-api:keeper_spaces", kwargs={"slug": "nonexistent-keeper"})
        response = client.get(url)

        assert response.status_code == 200
        assert response.json() == []

    def test_get_sessions_history(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        for _ in range(5):
            event = SessionFactory(space__published=True, cancelled=False)
            event.joined.add(user)

        url = reverse("mobile-api:sessions_history")
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_sessions_history_empty(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        url = reverse("mobile-api:sessions_history")
        response = client.get(url)

        assert response.status_code == 200
        assert response.json() == []

    def test_sessions_history_filters_unpublished_and_cancelled(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user

        event1 = SessionFactory(space__published=True, cancelled=False)
        event1.joined.add(user)

        event2 = SessionFactory(space__published=False, cancelled=False)
        event2.joined.add(user)

        event3 = SessionFactory(space__published=True, cancelled=False)
        event3.joined.add(user)
        event3.cancelled = True
        event3.save()

        url = reverse("mobile-api:sessions_history")
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["slug"] == event1.slug

    def test_sessions_history_limit(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        for _ in range(12):
            event = SessionFactory(space__published=True, cancelled=False)
            event.joined.add(user)

        url = reverse("mobile-api:sessions_history")
        response = client.get(url)

        assert response.status_code == 200
        assert len(response.json()) == 10

    def test_recommended_spaces(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:recommended_spaces")

        SessionFactory(space__published=True)
        SessionFactory(space__published=True)
        SessionFactory(space__published=True)
        SessionFactory(space__published=True)

        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_recommended_spaces_with_limit(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:recommended_spaces")

        for _ in range(5):
            SessionFactory(space__published=True, cancelled=False, listed=True)

        response = client.get(url, {"limit": 2})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_summary_upcoming_section(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        OnboardModelFactory(user=user)

        # This event should appear in the 'upcoming' list
        attending_event = SessionFactory(start=timezone.now() + timedelta(days=5))
        attending_event.attendees.add(user)

        # This event should NOT appear, as the user is not an attendee
        SessionFactory(start=timezone.now() + timedelta(days=5))

        url = reverse("mobile-api:spaces_summary")
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()

        assert len(data["upcoming"]) == 1
        assert data["upcoming"][0]["slug"] == attending_event.slug

    def test_upcoming_session_includes_in_progress_and_future(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        now = timezone.now()

        # 1. Event that started 30 minutes ago and lasts for 60 minutes (should be included)
        in_progress_event = SessionFactory(start=now - timedelta(minutes=30), duration_minutes=60)
        in_progress_event.attendees.add(user)

        # 2. Event that will start in 1 day (should be included)
        future_event = SessionFactory(start=now + timedelta(days=1))
        future_event.attendees.add(user)

        # 3. Event that ended 30 minutes ago (should NOT be included)
        past_event = SessionFactory(start=now - timedelta(minutes=90), duration_minutes=60)
        past_event.attendees.add(user)

        # 4. A cancelled event that is upcoming (should NOT be included)
        cancelled_event = SessionFactory(start=now + timedelta(hours=2), cancelled=True)
        cancelled_event.attendees.add(user)

        # 5. An event the user is not attending (should NOT be included)
        SessionFactory(start=now + timedelta(hours=3))

        response = client.get(reverse("mobile-api:spaces_summary"))

        assert response.status_code == 200
        data = response.json()

        upcoming_sessions_context = data["upcoming"]

        assert len(upcoming_sessions_context) == 2

    def test_summary_for_you_section(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        OnboardModelFactory(user=user)
        self_category = SpaceCategoryFactory(name="self")
        love_category = SpaceCategoryFactory(name="love")

        # Create a space the user is subscribed to with a different category
        subscribed_space = SpaceFactory(categories=[self_category])
        subscribed_space.subscribed.add(user)
        SessionFactory(space=subscribed_space, start=timezone.now() + timedelta(days=3))

        # This session has a non-matching category and should not be recommended
        non_matching_space = SpaceFactory(categories=[love_category])
        SessionFactory(start=timezone.now() + timedelta(days=4), space=non_matching_space)

        url = reverse("mobile-api:spaces_summary")
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()

        assert len(data["for_you"]) == 1
        for_you_slugs = {item["slug"] for item in data["for_you"]}
        assert subscribed_space.slug in for_you_slugs

    def test_summary_explore_section(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        OnboardModelFactory(user=user)

        # This space has an upcoming session and should appear in 'explore'
        explore_space_1 = SpaceFactory()
        SessionFactory(space=explore_space_1, start=timezone.now() + timedelta(days=10))

        # This space only has past sessions and should NOT appear
        past_session_space = SpaceFactory()
        SessionFactory(space=past_session_space, start=timezone.now() - timedelta(days=1))

        # This space is unpublished and should NOT appear
        unpublished_space = SpaceFactory(published=False)
        SessionFactory(space=unpublished_space, start=timezone.now() + timedelta(days=5))

        url = reverse("mobile-api:spaces_summary")
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()

        explore_slugs = {item["slug"] for item in data["explore"]}
        assert explore_space_1.slug in explore_slugs
        assert past_session_space.slug not in explore_slugs
        assert unpublished_space.slug not in explore_slugs

    def test_summary_no_onboard_model(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        # Don't create OnboardModel
        # Create some spaces to ensure we have something to return
        space = SpaceFactory(published=True)
        SessionFactory(space=space, start=timezone.now() + timedelta(days=5))

        url = reverse("mobile-api:spaces_summary")
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        # Should return empty for_you section but still have explore section
        assert "for_you" in data
        assert "explore" in data
        assert "upcoming" in data

    def test_summary_upcoming_spaces_excluded_from_for_you_and_explore(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        OnboardModelFactory(user=user)
        self_category = SpaceCategoryFactory(name="self")

        # Create a space that would normally appear in for_you (user is subscribed and has matching category)
        upcoming_space = SpaceFactory(categories=[self_category], published=True)
        upcoming_space.subscribed.add(user)

        # Create an upcoming session for this space that the user is attending
        upcoming_session = SessionFactory(space=upcoming_space, start=timezone.now() + timedelta(days=5))
        upcoming_session.attendees.add(user)

        # Create another space that should appear in for_you (to ensure for_you is not empty)
        for_you_space = SpaceFactory(categories=[self_category], published=True)
        for_you_space.subscribed.add(user)
        SessionFactory(space=for_you_space, start=timezone.now() + timedelta(days=10))

        # Create another space that should appear in explore (to ensure explore is not empty)
        explore_space = SpaceFactory(published=True)
        SessionFactory(space=explore_space, start=timezone.now() + timedelta(days=7))

        url = reverse("mobile-api:spaces_summary")
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()

        upcoming_slugs = {item["slug"] for item in data["upcoming"]}
        assert upcoming_session.slug in upcoming_slugs

        for_you_slugs = {item["slug"] for item in data["for_you"]}
        assert upcoming_space.slug not in for_you_slugs
        assert for_you_space.slug in for_you_slugs

        explore_slugs = {item["slug"] for item in data["explore"]}
        assert upcoming_space.slug not in explore_slugs
        assert explore_space.slug in explore_slugs

    def test_rsvp_confirm(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True)
        url = reverse("mobile-api:rsvp_confirm", kwargs={"event_slug": event.slug})

        response = client.post(url)

        assert response.status_code == 200

        data = response.json()
        assert data["slug"] == event.slug
        assert data["attending"] is True

        assert event.attendees.filter(pk=user.pk).exists()
        assert event.space.subscribed.filter(pk=user.pk).exists()

    def test_rsvp_cancel(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True)
        event.attendees.add(user)
        url = reverse("mobile-api:rsvp_cancel", kwargs={"event_slug": event.slug})

        response = client.delete(url)

        assert response.status_code == 200

        data = response.json()
        assert data["slug"] == event.slug
        assert data["attending"] is False

        assert not event.attendees.filter(pk=user.pk).exists()

    def test_rsvp_cancel_event_started(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True, cancelled=False, start=timezone.now() - timedelta(hours=1))
        event.attendees.add(user)

        url = reverse("mobile-api:rsvp_cancel", kwargs={"event_slug": event.slug})
        response = client.delete(url)

        assert response.status_code == 403
        assert "already started" in response.json()["detail"].lower()
        assert event.attendees.filter(pk=user.pk).exists()

    def test_rsvp_cancel_event_cancelled(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True, cancelled=True)
        event.attendees.add(user)

        url = reverse("mobile-api:rsvp_cancel", kwargs={"event_slug": event.slug})
        response = client.delete(url)

        assert response.status_code == 403
        assert "cancelled" in response.json()["detail"].lower()
        assert event.attendees.filter(pk=user.pk).exists()

    def test_rsvp_confirm_cannot_attend(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True, cancelled=True)
        url = reverse("mobile-api:rsvp_confirm", kwargs={"event_slug": event.slug})
        response = client.post(url)
        assert response.status_code == 403
        assert response.json()["detail"]
        assert not event.attendees.filter(pk=user.pk).exists()

    def test_rsvp_confirm_already_attending(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True, cancelled=False)
        event.attendees.add(user)

        url = reverse("mobile-api:rsvp_confirm", kwargs={"event_slug": event.slug})
        response = client.post(url)

        assert response.status_code == 403
        assert "already attending" in response.json()["detail"].lower()

    def test_rsvp_confirm_event_closed(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True, cancelled=False, open=False)

        url = reverse("mobile-api:rsvp_confirm", kwargs={"event_slug": event.slug})
        response = client.post(url)

        assert response.status_code == 403
        assert "not available" in response.json()["detail"].lower()
        assert not event.attendees.filter(pk=user.pk).exists()

    def test_rsvp_confirm_event_started(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True, cancelled=False, start=timezone.now() - timedelta(hours=1))

        url = reverse("mobile-api:rsvp_confirm", kwargs={"event_slug": event.slug})
        response = client.post(url)

        assert response.status_code == 403
        assert "already started" in response.json()["detail"].lower()
        assert not event.attendees.filter(pk=user.pk).exists()

    def test_rsvp_confirm_no_seats_left(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory(space__published=True, cancelled=False, seats=2)
        # Fill all seats
        other_user1 = UserFactory()
        other_user2 = UserFactory()
        event.attendees.add(other_user1, other_user2)

        url = reverse("mobile-api:rsvp_confirm", kwargs={"event_slug": event.slug})
        response = client.post(url)

        assert response.status_code == 403
        assert "no spots left" in response.json()["detail"].lower() or "spots" in response.json()["detail"].lower()
        assert not event.attendees.filter(pk=user.pk).exists()

    def test_post_session_feedback_up(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()
        event.attendees.add(user)

        url = reverse("mobile-api:session_feedback", kwargs={"event_slug": event.slug})
        response = client.post(
            url,
            {"feedback": "up"},
            content_type="application/json",
        )

        assert response.status_code == 204
        feedback = SessionFeedback.objects.get(session=event, user=user)
        assert feedback.feedback == SessionFeedbackOptions.UP
        assert feedback.message == ""

    def test_post_session_feedback_down(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()
        event.attendees.add(user)

        url = reverse("mobile-api:session_feedback", kwargs={"event_slug": event.slug})
        response = client.post(
            url,
            {"feedback": "down", "message": "It was not good."},
            content_type="application/json",
        )

        assert response.status_code == 204
        feedback = SessionFeedback.objects.get(session=event, user=user)
        assert feedback.feedback == SessionFeedbackOptions.DOWN
        assert feedback.message == "It was not good."

    def test_post_session_feedback_down_no_message(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()
        event.attendees.add(user)

        url = reverse("mobile-api:session_feedback", kwargs={"event_slug": event.slug})
        response = client.post(
            url,
            {"feedback": "down"},
            content_type="application/json",
        )

        assert response.status_code == 204
        feedback = SessionFeedback.objects.get(session=event, user=user)
        assert feedback.feedback == SessionFeedbackOptions.DOWN
        assert feedback.message == ""

    def test_post_session_feedback_not_attendee(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        event = SessionFactory()

        url = reverse("mobile-api:session_feedback", kwargs={"event_slug": event.slug})
        response = client.post(
            url,
            {"feedback": "up"},
            content_type="application/json",
        )

        assert response.status_code == 403
        assert "not an attendee" in response.json()["detail"].lower()

    def test_post_session_feedback_update(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()
        event.attendees.add(user)
        SessionFeedback.objects.create(session=event, user=user, feedback=SessionFeedbackOptions.DOWN, message="old")

        url = reverse("mobile-api:session_feedback", kwargs={"event_slug": event.slug})
        response = client.post(
            url,
            {"feedback": "up"},
            content_type="application/json",
        )

        assert response.status_code == 204
        feedback = SessionFeedback.objects.get(session=event, user=user)
        assert feedback.feedback == SessionFeedbackOptions.UP
        assert feedback.message == ""
        assert SessionFeedback.objects.count() == 1

    def test_post_session_feedback_invalid_value(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        event = SessionFactory()
        event.attendees.add(user)

        url = reverse("mobile-api:session_feedback", kwargs={"event_slug": event.slug})
        response = client.post(
            url,
            {"feedback": "invalid"},
            content_type="application/json",
        )

        assert response.status_code == 422
