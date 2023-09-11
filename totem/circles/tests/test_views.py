from django.urls import reverse

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
