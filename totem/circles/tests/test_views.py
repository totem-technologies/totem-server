import datetime

import pytest
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from totem.users.tests.factories import UserFactory

from ..views import AUTO_RSVP_SESSION_KEY
from .factories import CircleCategoryFactory, CircleEventFactory, CircleFactory


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
        circle = CircleEventFactory()
        url = reverse("circles:detail", kwargs={"slug": circle.circle.slug})
        response = client.get(url)
        assert response.status_code == 200

    def test_detail_circle_no_event(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        circle = CircleFactory()
        url = reverse("circles:detail", kwargs={"slug": circle.slug})
        response = client.get(url)
        assert response.status_code == 200


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

    def test_list_with_category_and_limit(self, client, db):
        category = CircleCategoryFactory()
        category2 = CircleCategoryFactory()
        circle = CircleFactory(categories=[category])
        circle2 = CircleFactory(categories=[category2])
        CircleEventFactory(circle=circle, start=timezone.now() + datetime.timedelta(days=1))
        CircleEventFactory(circle=circle2, start=timezone.now() + datetime.timedelta(days=2))
        url = reverse("circles:list")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert circle.title in content
        assert category.name in content
        assert circle2.title in content
        assert category2.name in content
        response = client.get(url, {"limit": 1})
        assert response.status_code == 200
        content = response.content.decode()
        assert circle.title in content
        assert circle2.title not in content
        response = client.get(url, {"category": category.slug, "limit": 15})
        assert response.status_code == 200
        assert circle.title in response.content.decode()
        assert category.name in response.content.decode()
        assert circle2.title not in response.content.decode()
        response = client.get(url, {"category": "empty", "limit": 15})
        assert response.status_code == 200
        assert circle.title not in response.content.decode()

    def test_list_with_invalid_limit(self, client, db):
        url = reverse("circles:list")
        with pytest.raises(ValueError):
            client.get(url, {"limit": "abc"})
        with pytest.raises(ValueError):
            client.get(url, {"limit": 101})


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

    def test_rsvp_auto_rsvp(self, client, db):
        """Test auto rsvp when user is not logged in, but then makes an account and goes back to the event page."""
        event = CircleEventFactory()
        response = client.post(reverse("circles:rsvp", kwargs={"event_slug": event.slug}), data={"action": "yes"})
        assert response.status_code == 302
        assert "signup" in response.url
        assert event.slug in response.url
        session = client.session
        assert session[AUTO_RSVP_SESSION_KEY] == event.slug
        user = UserFactory()
        user.save()
        client.force_login(user)
        response = client.get(reverse("circles:event_detail", kwargs={"event_slug": event.slug}))
        assert response.status_code == 200
        assert user in event.attendees.all()
        message = list(get_messages(response.wsgi_request))
        assert "spot" in message[0].message.lower()
