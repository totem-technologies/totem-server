from django.test import TestCase

from totem.users.tests.factories import UserFactory

from ..views import ics_hash
from .factories import CircleFactory


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

    def test_seats_left(self):
        circle = CircleFactory()
        self.assertEqual(circle.seats_left(), 8)
        user = UserFactory()
        circle.attendees.add(user)
        self.assertEqual(circle.seats_left(), 7)
        circle.attendees.add(user)
        self.assertEqual(circle.seats_left(), 7)
        circle.attendees.remove(user)
        self.assertEqual(circle.seats_left(), 8)

    def test_attendee_list(self):
        circle = CircleFactory()
        self.assertEqual(circle.attendee_list(), "")
        user = UserFactory()
        circle.attendees.add(user)
        assert user.email in circle.attendee_list()
