from django.core.exceptions import ValidationError
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


# class CircleEventModelTest(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         # Set up non-modified objects used by all test methods
#         user = User.objects.create_user(username="testuser", password="12345")
#         circle = Circle.objects.create(
#             title="Test Circle", subtitle="Test subtitle", author=user, price=10, duration="1 hour", recurring="Never"
#         )
#         CircleEvent.objects.create(start="2022-01-01 00:00:00", duration_minutes=60, seats=10, circle=circle)

#     def test_seats_left(self):
#         event = CircleEvent.objects.get(id=1)
#         self.assertEqual(event.seats_left(), 10)

#     def test_attendee_list(self):
#         event = CircleEvent.objects.get(id=1)
#         self.assertEqual(event.attendee_list(), "")

#     def test_get_absolute_url(self):
#         event = CircleEvent.objects.get(id=1)
#         # This will also fail if the urlconf is not defined.
#         self.assertEqual(event.get_absolute_url(), "/circles/test-circle/events/test-circle-1/")
