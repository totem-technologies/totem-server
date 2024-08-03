from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from totem.circles.api import EventCalendarFilterSchema, EventsFilterSchema
from totem.circles.tests.factories import CircleCategoryFactory, CircleEventFactory, CircleFactory
from totem.users.tests.factories import UserFactory


class TestCircleListAPI:
    def test_get_circle_list_bad_category(self, client, db):
        response = client.get(
            reverse("api-1:circles_list"), EventsFilterSchema(category="empty", author=""), format="json"
        )
        assert response.status_code == 200
        assert response.json() == {"count": 0, "items": []}

    def test_get_circle_list(self, client, db):
        event = CircleEventFactory()
        event.save()
        response = client.get(reverse("api-1:circles_list"), EventsFilterSchema(category="", author=""), format="json")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_circle_list_filters_category(self, client, db):
        category = CircleCategoryFactory()
        circle = CircleFactory(categories=[category])
        event = CircleEventFactory(circle=circle)
        event.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(
            reverse("api-1:circles_list"),
            EventsFilterSchema(category=category.slug, author=""),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_circle_list_filters_author(self, client, db):
        circle = CircleFactory()
        event = CircleEventFactory(circle=circle)
        event.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(
            reverse("api-1:circles_list"),
            EventsFilterSchema(category="", author=circle.author.slug),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_get_circle_list_limit(self, client, db):
        event = CircleEventFactory()
        event.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(
            reverse("api-1:circles_list"),
            EventsFilterSchema(category="", author=""),
            format="json",
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2
        response = client.get(
            reverse("api-1:circles_list"),
            EventsFilterSchema(category="", author="").model_dump() | {"limit": 1},
            format="json",
        )
        print(response.wsgi_request)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1


class TestFilterOptions:
    def test_get_filter_options(self, client, db):
        # past events should not be included
        past_event = CircleEventFactory(start=timezone.now() - timedelta(days=1))
        past_event.save()
        category = CircleCategoryFactory()
        circle = CircleFactory(categories=[category])
        event = CircleEventFactory(circle=circle)
        event.save()
        event2 = CircleEventFactory()
        event2.save()
        response = client.get(reverse("api-1:circle_filter_options"), format="json")
        assert response.status_code == 200
        assert len(response.json()["categories"]) == 1
        assert len(response.json()["authors"]) == 2
        assert response.json()["categories"][0]["slug"] == category.slug
        assert response.json()["categories"][0]["name"] == category.name
        slugs = [response.json()["authors"][0]["slug"], response.json()["authors"][1]["slug"]]
        assert circle.author.slug in slugs
        assert event2.circle.author.slug in slugs
        names = [response.json()["authors"][0]["name"], response.json()["authors"][1]["name"]]
        assert circle.author.name in names
        assert event2.circle.author.name in names


class TestEventDetail:
    def test_event_detail(self, client, db):
        event = CircleEventFactory()
        url = reverse("api-1:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["slug"] == event.slug

    def test_event_detail_not_found(self, client, db):
        url = reverse("api-1:event_detail", kwargs={"event_slug": "not-found"})
        response = client.get(url)
        assert response.status_code == 404

    def test_event_detail_authenticated(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        event = CircleEventFactory()
        url = reverse("api-1:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["slug"] == event.slug
        assert response.json()["attending"] is False

    def test_event_detail_ended(self, client, db):
        user = UserFactory()
        user.save()
        client.force_login(user)
        now_minus_one = timezone.now() - timedelta(days=1)
        event = CircleEventFactory(start=now_minus_one)
        event.attendees.add(user)
        url = reverse("api-1:event_detail", kwargs={"event_slug": event.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["ended"] is True
        assert response.json()["attending"] is True
        assert len(response.json()["attendees"]) == 0


class TestEventCalendar:
    def test_event_calendar_future(self, client, db):
        now_plus_week = timezone.now() + timedelta(days=7)
        event = CircleEventFactory(start=now_plus_week)
        url = reverse("api-1:event_calendar")
        response = client.get(
            url,
            EventCalendarFilterSchema(
                space_slug=event.circle.slug, month=now_plus_week.month, year=now_plus_week.year
            ).model_dump(),
        )
        assert response.status_code == 200
        assert response.json()[0]["title"] == event.title

    def test_event_calendar_now(self, client, db):
        now = timezone.now()
        event = CircleEventFactory(start=now)
        CircleEventFactory(start=now, cancelled=True)
        url = reverse("api-1:event_calendar")
        response = client.get(
            url,
            EventCalendarFilterSchema(space_slug=event.circle.slug, month=now.month, year=now.year).model_dump(),
        )
        assert response.status_code == 200
        assert response.json()[0]["title"] == event.title
        assert len(response.json()) == 1
