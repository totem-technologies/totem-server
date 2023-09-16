import datetime

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
        # event = CircleEventFactory()
        # event.start = timezone.now() + datetime.timedelta(minutes=20)
        event = CircleEventFactory(
            start=timezone.now() + datetime.timedelta(minutes=20),
        )
        event.save()
        user = UserFactory()
        user.save()
        event.add_attendee(user)
        client.force_login(user)
        response = client.get(reverse("circles:join", kwargs={"event_slug": event.slug}))
        assert response.status_code == 302
        assert "example" in response.url
        assert user in event.joined.all()
