import datetime

from django.contrib.messages import get_messages
from django.core import mail
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from totem.users.tests.factories import UserFactory

from ..actions import JoinSessionAction
from .factories import SessionFactory, SpaceFactory


class TestSpaceDetailView:
    def test_detail_loggedin(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        session = SessionFactory()
        session.add_attendee(user)
        url = reverse("spaces:session_detail", kwargs={"session_slug": session.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_detail(self, client, db):
        session = SessionFactory()
        url = reverse("spaces:session_detail", kwargs={"session_slug": session.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert "About this Session" not in response.content.decode()

    def test_detail_space(self, client, db):
        session = SessionFactory()
        url = reverse("spaces:detail", kwargs={"slug": session.space.slug})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("spaces:session_detail", kwargs={"session_slug": session.slug})

    def test_detail_next_session_space(self, client, db):
        # Make sure the details page still shows a session while it's in the grace period
        session_now = SessionFactory(start=timezone.now() - datetime.timedelta(minutes=5))
        url = reverse("spaces:detail", kwargs={"slug": session_now.space.slug})
        response = client.get(url)
        assert response.status_code == 302
        assert "This Space has no upcoming" not in response.content.decode()

    def test_detail_space_skips_unlisted_session(self, client, db):
        # An unlisted session is only reachable by direct link; the space page
        # redirects everyone else to the next listed session.
        space = SpaceFactory()
        unlisted = SessionFactory(space=space, start=timezone.now() + datetime.timedelta(hours=1), listed=False)
        listed = SessionFactory(space=space, start=timezone.now() + datetime.timedelta(days=2))
        url = reverse("spaces:detail", kwargs={"slug": space.slug})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("spaces:session_detail", kwargs={"session_slug": listed.slug})

        # Attendees of the unlisted session land on it instead.
        user = UserFactory()
        unlisted.add_attendee(user)
        client.force_login(user)
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("spaces:session_detail", kwargs={"session_slug": unlisted.slug})

    def test_detail_space_no_session(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        space = SpaceFactory()
        url = reverse("spaces:detail", kwargs={"slug": space.slug})
        response = client.get(url)
        assert response.status_code == 200


class TestSessionView:
    def test_event_logged_in(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        event = SessionFactory()
        event.add_attendee(user)
        url = reverse("spaces:session_detail", kwargs={"session_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_event(self, client, db):
        event = SessionFactory()
        url = reverse("spaces:session_detail", kwargs={"session_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_event_no_attendee(self, client, db):
        event = SessionFactory()
        url = reverse("spaces:session_detail", kwargs={"session_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_event_no_attendee_unauth(self, client, db):
        event = SessionFactory()
        url = reverse("spaces:session_detail", kwargs={"session_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_unlisted_session_page_not_indexable(self, client, db):
        # Unlisted sessions are reachable by direct link but must not be
        # search-indexable.
        listed = SessionFactory(content="A description for this session.")
        response = client.get(reverse("spaces:session_detail", kwargs={"session_slug": listed.slug}))
        assert "noindex" not in response.content.decode()

        unlisted = SessionFactory(listed=False, content="A description for this session.")
        response = client.get(reverse("spaces:session_detail", kwargs={"session_slug": unlisted.slug}))
        assert response.status_code == 200
        assert '<meta name="robots" content="noindex" />' in response.content.decode()

    def test_session_without_own_content_not_indexable(self, client, db):
        # A session with no description of its own is a copy of its space's
        # page with a different date. Keep those out of the index so every
        # session of a recurring space doesn't compete as a duplicate.
        for content in (None, "", "   "):
            session = SessionFactory(content=content)
            response = client.get(reverse("spaces:session_detail", kwargs={"session_slug": session.slug}))
            assert response.status_code == 200
            assert '<meta name="robots" content="noindex" />' in response.content.decode()

    def test_session_page_title_and_description_are_session_specific(self, client, db):
        space = SpaceFactory(title="What is Love?", content="Space level description of the topic.")
        start = timezone.make_aware(datetime.datetime(2026, 9, 12, 17, 0))

        titled = SessionFactory(space=space, start=start, title="Week 3: Boundaries", content="Session text here.")
        content = client.get(reverse("spaces:session_detail", kwargs={"session_slug": titled.slug})).content.decode()
        assert "Week 3: Boundaries - Sep 12, 2026 - Totem Spaces" in content
        assert 'content="Session text here." />' in content

        untitled = SessionFactory(space=space, start=start, content="Session text here.")
        content = client.get(reverse("spaces:session_detail", kwargs={"session_slug": untitled.slug})).content.decode()
        assert "What is Love? - Sep 12, 2026 - Totem Spaces" in content

        empty = SessionFactory(space=space, start=start + datetime.timedelta(days=7), content=None)
        content = client.get(reverse("spaces:session_detail", kwargs={"session_slug": empty.slug})).content.decode()
        assert 'content="Space level description of the topic." />' in content

    # def test_event_with_token(self, client, db):
    #     event = SessionFactory()
    #     user = UserFactory()
    #     user.save()
    #     url = AttendSpaceAction(user=user, parameters={"session_slug": event.slug}).build_url()
    #     response = client.get(url)
    #     assert response.status_code == 200
    #     assert user in event.attendees.all()
    #     assert "successfully reserved" in list(get_messages(response.wsgi_request))[0].message

    # def test_event_with_token_wrong_user(self, client, db):
    #     event = SessionFactory()
    #     user = UserFactory()
    #     user.save()
    #     client.force_login(user)
    #     user2 = UserFactory()
    #     user2.save()
    #     url = AttendSpaceAction(user=user2, parameters={"session_slug": event.slug}).build_url()
    #     response = client.get(url)
    #     assert response.status_code == 200
    #     assert user not in event.attendees.all()
    #     assert user2 not in event.attendees.all()

    # def test_event_with_token_user_already_attending(self, client, db):
    #     event = SessionFactory()
    #     user = UserFactory()
    #     user.save()
    #     event.add_attendee(user)
    #     url = AttendSpaceAction(user=user, parameters={"session_slug": event.slug}).build_url()
    #     response = client.get(url)
    #     assert response.status_code == 200
    #     assert user in event.attendees.all()
    #     assert list(get_messages(response.wsgi_request))[0].message == "You are already attending this session"

    # def test_event_with_token_wrong_event(self, client, db):
    #     event = SessionFactory()
    #     user = UserFactory()
    #     user.save()
    #     url = AttendSpaceAction(user=user, parameters={"session_slug": "wrong"}).build_url()
    #     token = url.split("=")[-1]
    #     bad_url = event.get_absolute_url() + f"?token={token}"
    #     response = client.get(bad_url)
    #     assert response.status_code == 200
    #     assert user not in event.attendees.all()
    #     assert "Invalid or expired link" in list(get_messages(response.wsgi_request))[0].message

    # def test_auto_rsvp_already_going(self, client, db):
    #     event = SessionFactory()
    #     user = UserFactory()
    #     user.save()
    #     event.add_attendee(user)
    #     event.save()
    #     client.force_login(user)
    #     session = client.session
    #     session[AUTO_RSVP_SESSION_KEY] = event.slug
    #     session.save()
    #     response = client.get(reverse("spaces:session_detail", kwargs={"session_slug": event.slug}))
    #     assert response.status_code == 200
    #     assert user in event.attendees.all()
    #     assert list(get_messages(response.wsgi_request))[0].message == "You are already attending this session"


class TestJoinView:
    def test_join_unauth(self, client, db):
        event = SessionFactory()
        response = client.get(reverse("spaces:join", kwargs={"session_slug": event.slug}))
        assert response.status_code == 302
        assert reverse("users:login") in response.url

    def test_join_not_attend(self, client, db):
        event = SessionFactory()
        user = UserFactory()
        user.save()
        client.force_login(user)
        response = client.get(reverse("spaces:join", kwargs={"session_slug": event.slug}))
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.joined.all()

    def test_join_attending(self, client, db):
        event = SessionFactory(
            start=timezone.now() + datetime.timedelta(minutes=14),
        )
        event.save()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        response = client.get(reverse("spaces:join", kwargs={"session_slug": event.slug}))
        assert response.status_code == 302
        assert event.room_url() in response.url
        assert user in event.joined.all()

    def test_join_attending_late(self, client, db):
        event = SessionFactory(start=timezone.now() + datetime.timedelta(minutes=20))
        event.save()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        event.start = timezone.now() - datetime.timedelta(minutes=30)
        event.save()
        response = client.get(reverse("spaces:join", kwargs={"session_slug": event.slug}))
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.joined.all()

    def test_join_with_token(self, client, db):
        event = SessionFactory(start=timezone.now() + datetime.timedelta(minutes=14))
        event.save()
        user = UserFactory()
        user.save()
        # Don't log in, just use the token
        event.add_attendee(user)
        url = JoinSessionAction(user=user, parameters={"session_slug": event.slug}).build_url()
        response = client.get(url)
        assert response.status_code == 302
        assert event.room_url() in response.url
        assert user in event.joined.all()


class AnonSubscribeViewTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.space = SpaceFactory()
        self.token_url = self.space.subscribe_url(self.user, subscribe=True)
        self.token_url_unsub = self.space.subscribe_url(self.user, subscribe=False)

    def test_anon_subscribe(self):
        self.assertFalse(self.user in self.space.subscribed.all())
        response = self.client.get(self.token_url)
        assert response.status_code == 302
        self.assertTrue(self.user in self.space.subscribed.all())

    def test_anon_subscribe_wrong_token(self):
        self.assertFalse(self.user in self.space.subscribed.all())
        response = self.client.get(self.token_url[:-3])
        assert response.status_code == 302
        self.assertFalse(self.user in self.space.subscribed.all())

    def test_anon_subscribe_no_token(self):
        self.assertFalse(self.user in self.space.subscribed.all())
        url = reverse("spaces:subscribe", args=[self.space.slug])
        response = self.client.get(url)
        assert response.status_code == 302
        self.assertFalse(self.user in self.space.subscribed.all())

    def test_anon_subscribe_unsubscribe(self):
        self.space.subscribe(self.user)
        self.assertTrue(self.user in self.space.subscribed.all())
        response = self.client.get(self.token_url_unsub)
        assert response.status_code == 302
        self.assertFalse(self.user in self.space.subscribed.all())


class CalendarViewTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.space = SpaceFactory()
        self.event = SessionFactory(space=self.space)
        self.event.add_attendee(self.user)

    def test_calendar(self):
        url = reverse("spaces:calendar", args=[self.event.slug])
        response = self.client.get(url)
        assert response.status_code == 200
        self.assertTemplateUsed(response, "spaces/calendaradd.html")
        self.assertTrue(self.user in self.event.attendees.all())

    def test_calendar_unauth(self):
        self.client.logout()
        url = reverse("spaces:calendar", args=[self.event.slug])
        response = self.client.get(url)
        assert response.status_code == 200
        assert self.space.title in response.content.decode()

    def test_calendar_unsubscribed(self):
        self.space.unsubscribe(self.user)
        url = reverse("spaces:calendar", args=[self.event.slug])
        response = self.client.get(url)
        assert response.status_code == 200
        assert self.space.title in response.content.decode()


class TestSpaceListView:
    def test_list(self, client, db):
        url = reverse("spaces:list")
        response = client.get(url)
        assert response.status_code == 200

    def test_list_loggedin(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        session = SessionFactory()
        session.add_attendee(user)
        url = reverse("spaces:list")
        response = client.get(url)
        assert response.status_code == 200


class TestRSVPView:
    def test_rsvp_unauth(self, client, db):
        event = SessionFactory()
        response = client.get(reverse("spaces:rsvp", kwargs={"session_slug": event.slug}))
        assert response.status_code == 302
        assert reverse("users:login") in response.url

    def test_rsvp_not_attend(self, client, db):
        event = SessionFactory()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        response = client.post(reverse("spaces:rsvp", kwargs={"session_slug": event.slug}), data={"action": "no"})
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.joined.all()

    def test_rsvp_unpublished_draft_rejected(self, client, db):
        user = UserFactory()
        client.force_login(user)
        session = SessionFactory(space__published=False)
        response = client.post(
            reverse("spaces:rsvp", kwargs={"session_slug": session.slug}),
            {"action": "add"},
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 400
        assert not session.attendees.filter(pk=user.pk).exists()

    def test_subscribe_unpublished_draft_rejected(self, client, db):
        user = UserFactory()
        client.force_login(user)
        space = SpaceFactory(published=False)
        response = client.post(reverse("spaces:subscribe", kwargs={"slug": space.slug}), {"action": "subscribe"})
        assert response.status_code == 403
        assert not space.subscribed.filter(pk=user.pk).exists()

    def test_rsvp_attending(self, client, db):
        event = SessionFactory(start=timezone.now() + datetime.timedelta(minutes=20))
        user = UserFactory()
        user.save()
        client.force_login(user)
        response = client.post(reverse("spaces:rsvp", kwargs={"session_slug": event.slug}), data={"action": "yes"})
        assert response.status_code == 302
        assert event.slug in response.url
        assert user in event.attendees.all()

    def test_rsvp_ajax_returns_conflicting_sessions(self, client, db):
        start = timezone.now() + datetime.timedelta(days=1)
        event = SessionFactory(title="New Session", start=start, duration_minutes=60)
        first = SessionFactory(title="Earlier Conflict", start=start, duration_minutes=30)
        second = SessionFactory(
            title="Later Conflict",
            start=start + datetime.timedelta(minutes=30),
            duration_minutes=60,
        )
        user = UserFactory()
        first.attendees.add(user)
        second.attendees.add(user)
        client.force_login(user)

        response = client.post(
            reverse("spaces:rsvp", kwargs={"session_slug": event.slug}),
            data={"action": "yes"},
            HTTP_ACCEPT="application/json",
        )

        assert response.status_code == 409
        data = response.json()
        assert data["message"] == "This session conflicts with one or more sessions you are attending"
        assert data["error"] == "This session conflicts with another one you're attending."
        assert [session["slug"] for session in data["conflicting_sessions"]] == [first.slug, second.slug]
        assert [session["title"] for session in data["conflicting_sessions"]] == [
            "Earlier Conflict",
            "Later Conflict",
        ]
        assert not event.attendees.filter(pk=user.pk).exists()

    def test_rsvp_ajax_conflict_queries_do_not_scale_with_conflicts(self, client, db):
        start = timezone.now() + datetime.timedelta(days=1)
        event = SessionFactory(start=start, duration_minutes=60)
        first = SessionFactory(start=start, duration_minutes=60)
        user = UserFactory()
        first.attendees.add(user)
        client.force_login(user)
        url = reverse("spaces:rsvp", kwargs={"session_slug": event.slug})

        with CaptureQueriesContext(connection) as one_conflict_queries:
            one_conflict_response = client.post(url, data={"action": "yes"}, HTTP_ACCEPT="application/json")

        second = SessionFactory(start=start + datetime.timedelta(minutes=30), duration_minutes=60)
        second.attendees.add(user)
        with CaptureQueriesContext(connection) as two_conflict_queries:
            two_conflict_response = client.post(url, data={"action": "yes"}, HTTP_ACCEPT="application/json")

        assert one_conflict_response.status_code == 409
        assert two_conflict_response.status_code == 409
        assert len(two_conflict_queries) == len(one_conflict_queries)

    def test_rsvp_attending_late(self, client, db):
        event = SessionFactory(start=timezone.now() - datetime.timedelta(minutes=20))
        event.save()
        user = UserFactory()
        user.save()
        client.force_login(user)
        response = client.post(reverse("spaces:rsvp", kwargs={"session_slug": event.slug}), data={"action": "yes"})
        message = list(get_messages(response.wsgi_request))
        assert message[0].message == "We couldn't update your RSVP right now. Please try again."
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.joined.all()
        assert user not in event.attendees.all()

    def test_rsvp_remove_redirects_to_next(self, client, db):
        event = SessionFactory()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        response = client.post(
            reverse("spaces:rsvp", kwargs={"session_slug": event.slug}),
            data={"action": "remove", "next": reverse("users:dashboard")},
        )
        assert response.status_code == 302
        assert response.url == reverse("users:dashboard")
        assert user not in event.attendees.all()

    def test_rsvp_unsafe_next_ignored(self, client, db):
        event = SessionFactory()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        response = client.post(
            reverse("spaces:rsvp", kwargs={"session_slug": event.slug}),
            data={"action": "remove", "next": "https://evil.example.com/"},
        )
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.attendees.all()

    # def test_rsvp_auto_rsvp(self, client, db):
    #     """Test auto rsvp when user is not logged in, but then makes an account and goes back to the event page."""
    #     event = SessionFactory()
    #     response = client.post(reverse("spaces:rsvp", kwargs={"session_slug": event.slug}), data={"action": "yes"})
    #     assert response.status_code == 302
    #     assert "signup" in response.url
    #     assert event.slug in response.url
    #     session = client.session
    #     assert session[AUTO_RSVP_SESSION_KEY] == event.slug
    #     user = UserFactory()
    #     user.save()
    #     client.force_login(user)
    #     response = client.get(reverse("spaces:session_detail", kwargs={"session_slug": event.slug}))
    #     assert response.status_code == 200
    #     assert user in event.attendees.all()
    #     message = list(get_messages(response.wsgi_request))
    #     assert "spot" in message[0].message.lower()
    #     assert client.session.get(AUTO_RSVP_SESSION_KEY) is None

    def test_attending_email_sent(self, client, db):
        # test that notify_session_signup is called when user RSVPs
        event = SessionFactory()
        event.save()
        user = UserFactory()
        user.save()
        client.force_login(user)
        client.post(reverse("spaces:rsvp", kwargs={"session_slug": event.slug}), data={"action": "yes"})
        assert mail.outbox[0].to == [user.email]
        assert "Spot Saved" in mail.outbox[0].body

    def test_attending_and_can_join_email_sent(self, client, db):
        # test that notify_session_starting is called when user RSVPs and the session is starting soon
        event = SessionFactory(notified=True, start=timezone.now() + datetime.timedelta(minutes=10))
        event.save()
        user = UserFactory()
        user.save()
        client.force_login(user)
        client.post(reverse("spaces:rsvp", kwargs={"session_slug": event.slug}), data={"action": "yes"})
        assert mail.outbox[0].to == [user.email]
        assert "Spot Saved" not in mail.outbox[0].body
        assert "Get Ready" in mail.outbox[0].body


class TestLegacyRedirects:
    """Tests for legacy URL redirects from the circles->spaces rename."""

    def test_events_redirect(self, client, db):
        """Test that /spaces/events/ redirects to /spaces/sessions/."""
        response = client.get("/spaces/events/")
        assert response.status_code == 301
        assert response.url == reverse("spaces:sessions")

    def test_event_detail_redirect(self, client, db):
        """Test that /spaces/event/<slug>/ redirects to /spaces/session/<slug>/."""
        event = SessionFactory()
        response = client.get(f"/spaces/event/{event.slug}/")
        assert response.status_code == 301
        assert response.url == reverse("spaces:session_detail", kwargs={"session_slug": event.slug})
