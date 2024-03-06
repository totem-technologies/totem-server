from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase

from totem.users.tests.factories import UserFactory

from ..views import ics_hash
from .factories import CircleEventFactory, CircleFactory


def test_ics_hash():
    slug = "my-slug"
    user_ics_key = 123456
    expected_hash = "e35dadad16952b194afc"
    assert ics_hash(slug, user_ics_key) == expected_hash


class CircleModelTest(TestCase):
    def test_title_label(self):
        circle = CircleFactory()
        field_label = circle._meta.get_field("title").verbose_name
        self.assertEqual(field_label, "title")

    def test_get_absolute_url(self):
        circle = CircleFactory()
        # This will also fail if the urlconf is not defined.
        self.assertEqual(circle.get_absolute_url(), f"/circles/{circle.slug}/")

    def test_subscribed_list(self):
        circle = CircleFactory()
        self.assertEqual(circle.subscribed_list(), "")

    def test_price_min_value(self):
        circle = CircleFactory()
        circle.price = -1
        with self.assertRaisesMessage(ValidationError, "Price must be greater than or equal to 0"):
            circle.full_clean()

    def test_price_max_value(self):
        circle = CircleFactory()
        circle.price = 1001
        with self.assertRaisesMessage(ValidationError, "Price must be less than or equal to 1000"):
            circle.full_clean()

    def test_subscribed(self):
        circle = CircleFactory()
        self.assertEqual(circle.subscribed.count(), 0)
        user = UserFactory()
        circle.subscribed.add(user)
        self.assertEqual(circle.subscribed.count(), 1)
        circle.subscribed.add(user)
        self.assertEqual(circle.subscribed.count(), 1)
        circle.subscribed.remove(user)
        self.assertEqual(circle.subscribed.count(), 0)


class TestCircleEventModel:
    def test_notify(self, db):
        user = UserFactory()
        event = CircleEventFactory()
        event.attendees.add(user)
        assert mail.outbox == []
        event.save()
        assert not event.notified
        event.notify()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/circles/join/" in message
        event.refresh_from_db()
        assert event.notified

    def test_advertise(self, db):
        user = UserFactory()
        event = CircleEventFactory()
        event.circle.subscribed.add(user)
        assert mail.outbox == []
        event.save()
        assert not event.advertised
        event.advertise()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/circles/event" in message
        assert "http://testserver/circles/subscribe" in message
        event.refresh_from_db()
        assert event.advertised

    def test_notify_tomorrow(self, db):
        user = UserFactory()
        event = CircleEventFactory()
        event.attendees.add(user)
        assert mail.outbox == []
        event.save()
        assert not event.notified_tomorrow
        event.notify_tomorrow()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/circles/event" in message
        event.refresh_from_db()
        assert event.notified_tomorrow
