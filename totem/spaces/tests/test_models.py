from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase

from totem.users.tests.factories import UserFactory

from ..views import ics_hash
from .factories import SessionFactory, SpaceFactory


def test_ics_hash():
    slug = "my-slug"
    user_ics_key = 123456
    expected_hash = "e35dadad16952b194afc"
    assert ics_hash(slug, user_ics_key) == expected_hash


class SpaceModelTest(TestCase):
    def test_title_label(self):
        space = SpaceFactory()
        field_label = space._meta.get_field("title").verbose_name  # type: ignore
        self.assertEqual(field_label, "title")

    def test_get_absolute_url(self):
        space = SpaceFactory()
        # This will also fail if the urlconf is not defined.
        self.assertEqual(space.get_absolute_url(), f"/spaces/{space.slug}/")

    def test_subscribed_list(self):
        space = SpaceFactory()
        self.assertEqual(space.subscribed_list(), "")

    def test_price_min_value(self):
        space = SpaceFactory()
        space.price = -1
        with self.assertRaisesMessage(ValidationError, "Price must be greater than or equal to 0"):
            space.full_clean()

    def test_price_max_value(self):
        space = SpaceFactory()
        space.price = 1001
        with self.assertRaisesMessage(ValidationError, "Price must be less than or equal to 1000"):
            space.full_clean()

    def test_subscribed(self):
        space = SpaceFactory()
        self.assertEqual(space.subscribed.count(), 0)
        user = UserFactory()
        space.subscribed.add(user)
        self.assertEqual(space.subscribed.count(), 1)
        space.subscribed.add(user)
        self.assertEqual(space.subscribed.count(), 1)
        space.subscribed.remove(user)
        self.assertEqual(space.subscribed.count(), 0)


class TestSessionModel:
    def test_notify(self, db):
        user = UserFactory()
        session = SessionFactory()
        session.attendees.add(user)
        assert mail.outbox == []
        session.save()
        assert not session.notified
        session.notify()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/spaces/join/" in message
        session.refresh_from_db()
        assert session.notified

    def test_advertise(self, db):
        user = UserFactory()
        session = SessionFactory()
        session.space.subscribed.add(user)
        assert mail.outbox == []
        session.save()
        assert not session.advertised
        session.advertise()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/spaces/session" in message
        assert "http://testserver/spaces/subscribe" in message
        session.refresh_from_db()
        assert session.advertised

    def test_notify_tomorrow(self, db):
        user = UserFactory()
        session = SessionFactory()
        session.attendees.add(user)
        assert mail.outbox == []
        session.save()
        assert not session.notified_tomorrow
        session.notify_tomorrow()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "http://testserver/spaces/session" in message
        session.refresh_from_db()
        assert session.notified_tomorrow
