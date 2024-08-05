import datetime

from django.contrib.messages import get_messages
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from totem.users.tests.factories import UserFactory

from ..actions import JoinCircleAction
from .factories import CircleEventFactory, CircleFactory


class TestCircleDetailView:
    def test_detail_loggedin(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        circle = CircleEventFactory()
        circle.add_attendee(user)
        url = reverse("circles:event_detail", kwargs={"event_slug": circle.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_detail(self, client, db):
        circle = CircleEventFactory()
        url = reverse("circles:event_detail", kwargs={"event_slug": circle.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_detail_circle(self, client, db):
        event = CircleEventFactory()
        url = reverse("circles:detail", kwargs={"slug": event.circle.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_detail_next_event_circle(self, client, db):
        # Make sure the details page still shows an event while it's in the grace period
        event_now = CircleEventFactory(start=timezone.now() - datetime.timedelta(minutes=5))
        url = reverse("circles:detail", kwargs={"slug": event_now.circle.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert "This Space has no upcoming" not in response.content.decode()

    def test_detail_circle_no_event(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        circle = CircleFactory()
        url = reverse("circles:detail", kwargs={"slug": circle.slug})
        response = client.get(url)
        assert response.status_code == 200


class TestCircleEventView:
    def test_event_logged_in(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        event = CircleEventFactory()
        event.add_attendee(user)
        url = reverse("circles:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_event(self, client, db):
        event = CircleEventFactory()
        url = reverse("circles:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_event_no_attendee(self, client, db):
        event = CircleEventFactory()
        url = reverse("circles:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_event_no_attendee_unauth(self, client, db):
        event = CircleEventFactory()
        url = reverse("circles:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200

    # def test_event_with_token(self, client, db):
    #     event = CircleEventFactory()
    #     user = UserFactory()
    #     user.save()
    #     url = AttendCircleAction(user=user, parameters={"event_slug": event.slug}).build_url()
    #     response = client.get(url)
    #     assert response.status_code == 200
    #     assert user in event.attendees.all()
    #     assert "successfully reserved" in list(get_messages(response.wsgi_request))[0].message

    # def test_event_with_token_wrong_user(self, client, db):
    #     event = CircleEventFactory()
    #     user = UserFactory()
    #     user.save()
    #     client.force_login(user)
    #     user2 = UserFactory()
    #     user2.save()
    #     url = AttendCircleAction(user=user2, parameters={"event_slug": event.slug}).build_url()
    #     response = client.get(url)
    #     assert response.status_code == 200
    #     assert user not in event.attendees.all()
    #     assert user2 not in event.attendees.all()

    # def test_event_with_token_user_already_attending(self, client, db):
    #     event = CircleEventFactory()
    #     user = UserFactory()
    #     user.save()
    #     event.add_attendee(user)
    #     url = AttendCircleAction(user=user, parameters={"event_slug": event.slug}).build_url()
    #     response = client.get(url)
    #     assert response.status_code == 200
    #     assert user in event.attendees.all()
    #     assert list(get_messages(response.wsgi_request))[0].message == "You are already attending this session"

    # def test_event_with_token_wrong_event(self, client, db):
    #     event = CircleEventFactory()
    #     user = UserFactory()
    #     user.save()
    #     url = AttendCircleAction(user=user, parameters={"event_slug": "wrong"}).build_url()
    #     token = url.split("=")[-1]
    #     bad_url = event.get_absolute_url() + f"?token={token}"
    #     response = client.get(bad_url)
    #     assert response.status_code == 200
    #     assert user not in event.attendees.all()
    #     assert "Invalid or expired link" in list(get_messages(response.wsgi_request))[0].message

    # def test_auto_rsvp_already_going(self, client, db):
    #     event = CircleEventFactory()
    #     user = UserFactory()
    #     user.save()
    #     event.add_attendee(user)
    #     event.save()
    #     client.force_login(user)
    #     session = client.session
    #     session[AUTO_RSVP_SESSION_KEY] = event.slug
    #     session.save()
    #     response = client.get(reverse("circles:event_detail", kwargs={"event_slug": event.slug}))
    #     assert response.status_code == 200
    #     assert user in event.attendees.all()
    #     assert list(get_messages(response.wsgi_request))[0].message == "You are already attending this session"


class TestJoinView:
    def test_join_unauth(self, client, db):
        event = CircleEventFactory()
        response = client.get(reverse("circles:join", kwargs={"event_slug": event.slug}))
        assert response.status_code == 302
        assert "signup" in response.url

    def test_join_not_attend(self, client, db):
        event = CircleEventFactory()
        user = UserFactory()
        user.save()
        client.force_login(user)
        response = client.get(reverse("circles:join", kwargs={"event_slug": event.slug}))
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.joined.all()

    def test_join_attending(self, client, db):
        event = CircleEventFactory(
            start=timezone.now() + datetime.timedelta(minutes=14),
        )
        event.save()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        response = client.get(reverse("circles:join", kwargs={"event_slug": event.slug}))
        assert response.status_code == 302
        assert event.meeting_url in response.url
        assert user in event.joined.all()

    def test_join_attending_late(self, client, db):
        event = CircleEventFactory(start=timezone.now() + datetime.timedelta(minutes=20))
        event.save()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        event.start = timezone.now() - datetime.timedelta(minutes=30)
        response = client.get(reverse("circles:join", kwargs={"event_slug": event.slug}))
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.joined.all()

    def test_join_with_token(self, client, db):
        event = CircleEventFactory(start=timezone.now() + datetime.timedelta(minutes=14))
        event.save()
        user = UserFactory()
        user.save()
        # Don't log in, just use the token
        event.add_attendee(user)
        url = JoinCircleAction(user=user, parameters={"event_slug": event.slug}).build_url()
        response = client.get(url)
        assert response.status_code == 302
        assert event.meeting_url in response.url
        assert user in event.joined.all()


class AnonSubscribeViewTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.circle = CircleFactory()
        self.token_url = self.circle.subscribe_url(self.user, subscribe=True)
        self.token_url_unsub = self.circle.subscribe_url(self.user, subscribe=False)

    def test_anon_subscribe(self):
        self.assertFalse(self.user in self.circle.subscribed.all())
        response = self.client.get(self.token_url)
        assert response.status_code == 302
        self.assertTrue(self.user in self.circle.subscribed.all())

    def test_anon_subscribe_wrong_token(self):
        self.assertFalse(self.user in self.circle.subscribed.all())
        response = self.client.get(self.token_url[:-3])
        assert response.status_code == 302
        self.assertFalse(self.user in self.circle.subscribed.all())

    def test_anon_subscribe_no_token(self):
        self.assertFalse(self.user in self.circle.subscribed.all())
        url = reverse("circles:subscribe", args=[self.circle.slug])
        response = self.client.get(url)
        assert response.status_code == 302
        self.assertFalse(self.user in self.circle.subscribed.all())

    def test_anon_subscribe_unsubscribe(self):
        self.circle.subscribe(self.user)
        self.assertTrue(self.user in self.circle.subscribed.all())
        response = self.client.get(self.token_url_unsub)
        assert response.status_code == 302
        self.assertFalse(self.user in self.circle.subscribed.all())


class CalendarViewTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.circle = CircleFactory()
        self.event = CircleEventFactory(circle=self.circle)
        self.event.add_attendee(self.user)

    def test_calendar(self):
        url = reverse("circles:calendar", args=[self.event.slug])
        response = self.client.get(url)
        assert response.status_code == 200
        self.assertTemplateUsed(response, "circles/calendaradd.html")
        self.assertTrue(self.user in self.event.attendees.all())

    def test_calendar_unauth(self):
        self.client.logout()
        url = reverse("circles:calendar", args=[self.event.slug])
        response = self.client.get(url)
        assert response.status_code == 200
        assert self.circle.title in response.content.decode()

    def test_calendar_unsubscribed(self):
        self.circle.unsubscribe(self.user)
        url = reverse("circles:calendar", args=[self.event.slug])
        response = self.client.get(url)
        assert response.status_code == 200
        assert self.circle.title in response.content.decode()


class TestCircleListView:
    def test_list(self, client, db):
        url = reverse("circles:list")
        response = client.get(url)
        assert response.status_code == 200

    def test_list_loggedin(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        circle = CircleEventFactory()
        circle.add_attendee(user)
        url = reverse("circles:list")
        response = client.get(url)
        assert response.status_code == 200


class TestRSVPView:
    def test_rsvp_unauth(self, client, db):
        event = CircleEventFactory()
        response = client.get(reverse("circles:rsvp", kwargs={"event_slug": event.slug}))
        assert response.status_code == 302
        assert "signup" in response.url

    def test_rsvp_not_attend(self, client, db):
        event = CircleEventFactory()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        response = client.post(reverse("circles:rsvp", kwargs={"event_slug": event.slug}), data={"action": "no"})
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.joined.all()

    def test_rsvp_attending(self, client, db):
        event = CircleEventFactory(start=timezone.now() + datetime.timedelta(minutes=20))
        user = UserFactory()
        user.save()
        client.force_login(user)
        response = client.post(reverse("circles:rsvp", kwargs={"event_slug": event.slug}), data={"action": "yes"})
        assert response.status_code == 302
        assert event.slug in response.url
        assert user in event.attendees.all()

    def test_rsvp_attending_late(self, client, db):
        event = CircleEventFactory(start=timezone.now() - datetime.timedelta(minutes=20))
        event.save()
        user = UserFactory()
        user.save()
        client.force_login(user)
        response = client.post(reverse("circles:rsvp", kwargs={"event_slug": event.slug}), data={"action": "yes"})
        message = list(get_messages(response.wsgi_request))
        assert "started" in message[0].message.lower()
        assert response.status_code == 302
        assert event.slug in response.url
        assert user not in event.joined.all()
        assert user not in event.attendees.all()

    # def test_rsvp_auto_rsvp(self, client, db):
    #     """Test auto rsvp when user is not logged in, but then makes an account and goes back to the event page."""
    #     event = CircleEventFactory()
    #     response = client.post(reverse("circles:rsvp", kwargs={"event_slug": event.slug}), data={"action": "yes"})
    #     assert response.status_code == 302
    #     assert "signup" in response.url
    #     assert event.slug in response.url
    #     session = client.session
    #     assert session[AUTO_RSVP_SESSION_KEY] == event.slug
    #     user = UserFactory()
    #     user.save()
    #     client.force_login(user)
    #     response = client.get(reverse("circles:event_detail", kwargs={"event_slug": event.slug}))
    #     assert response.status_code == 200
    #     assert user in event.attendees.all()
    #     message = list(get_messages(response.wsgi_request))
    #     assert "spot" in message[0].message.lower()
    #     assert client.session.get(AUTO_RSVP_SESSION_KEY) is None

    def test_attending_email_sent(self, client, db):
        # test that send_notify_circle_signup is called when user RSVPs
        event = CircleEventFactory()
        event.save()
        user = UserFactory()
        user.save()
        client.force_login(user)
        client.post(reverse("circles:rsvp", kwargs={"event_slug": event.slug}), data={"action": "yes"})
        assert mail.outbox[0].to == [user.email]
        assert "Spot Saved" in mail.outbox[0].body

    def test_attending_and_can_join_email_sent(self, client, db):
        # test that send_notify_circle_starting is called when user RSVPs and the event is starting soon
        event = CircleEventFactory(notified=True, start=timezone.now() + datetime.timedelta(minutes=10))
        event.save()
        user = UserFactory()
        user.save()
        client.force_login(user)
        client.post(reverse("circles:rsvp", kwargs={"event_slug": event.slug}), data={"action": "yes"})
        assert mail.outbox[0].to == [user.email]
        assert "Spot Saved" not in mail.outbox[0].body
        assert "Get Ready" in mail.outbox[0].body
