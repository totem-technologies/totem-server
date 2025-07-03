import pytest
from django.test import Client
from django.urls import reverse

from totem.circles.tests.factories import CircleEventFactory, CircleFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestMobileApiSpaces:
    def test_subscribe_to_space(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        space = CircleFactory(published=True)

        url = reverse("mobile-api:spaces_subscribe", kwargs={"space_slug": space.slug})
        response = client.post(url)

        assert response.status_code == 200
        assert response.json() is True
        assert space.subscribed.filter(pk=user.pk).exists()

    def test_unsubscribe_from_space(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        space = CircleFactory(published=True)
        space.subscribed.add(user)

        url = reverse("mobile-api:spaces_unsubscribe", kwargs={"space_slug": space.slug})
        response = client.delete(url)

        assert response.status_code == 200
        assert response.json() is True
        assert not space.subscribed.filter(pk=user.pk).exists()

    def test_list_subscriptions(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        space1 = CircleFactory(published=True)
        space2 = CircleFactory(published=True)
        CircleFactory(published=True)

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
        event = CircleEventFactory()
        event.save()

        url = reverse("mobile-api:mobile_spaces_list")
        response = client.get(url)

        assert response.status_code == 200
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["slug"] == event.circle.slug

    def test_list_spaces_no_events(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        response = client.get(reverse("mobile-api:mobile_spaces_list"))
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_get_space_detail(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user
        event = CircleEventFactory(circle__published=True)
        space = event.circle

        url = reverse("mobile-api:spaces_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == event.slug
        assert data["space_title"] == space.title
        assert data["space"]["slug"] == space.slug

    def test_get_keeper_spaces(self, client_with_user: tuple[Client, User]):
        client, _ = client_with_user

        keeper1 = UserFactory(is_staff=True)
        circle = CircleFactory(author=keeper1, published=True)
        CircleEventFactory(circle=circle)

        url = reverse("mobile-api:keeper_spaces", kwargs={"slug": keeper1.slug})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["slug"] == circle.slug
