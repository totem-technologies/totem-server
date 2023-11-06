import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from totem.users.tests.factories import UserFactory

from .factories import CircleEventFactory, CircleFactory


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
        assert "login" in response.url

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
        self.token = self.circle.subscribe_token(self.user)

    def test_anon_subscribe(self):
        url = reverse("circles:subscribe", args=[self.circle.slug])
        response = self.client.get(f"{url}?user={self.user.slug}&token={self.token}")
        assert response.status_code == 200
        self.assertTemplateUsed(response, "circles/subscribed.html")
        self.assertTrue(self.user in self.circle.subscribed.all())

    def test_anon_subscribe_wrong_token(self):
        url = reverse("circles:subscribe", args=[self.circle.slug])
        response = self.client.get(f"{url}?user={self.user.slug}&token=wrong-token")
        assert response.status_code == 403
        self.assertFalse(self.user in self.circle.subscribed.all())

    def test_anon_subscribe_no_token(self):
        url = reverse("circles:subscribe", args=[self.circle.slug])
        response = self.client.get(f"{url}?user={self.user.slug}")
        assert response.status_code == 200
        self.assertTemplateUsed(response, "circles/subscribed.html")
        self.assertFalse(self.user in self.circle.subscribed.all())

    def test_anon_subscribe_unsubscribe(self):
        url = reverse("circles:subscribe", args=[self.circle.slug])
        response = self.client.get(f"{url}?user={self.user.slug}&token={self.token}&action=unsubscribe")
        assert response.status_code == 200
        self.assertTemplateUsed(response, "circles/subscribed.html")
        self.assertTrue(response.context["unsubscribed"])
        self.assertFalse(self.user in self.circle.subscribed.all())
