import datetime

from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from totem.users.tests.factories import UserFactory

from ..models import Circle, CircleEvent


class CircleFactory(DjangoModelFactory):
    title = Faker("name")
    subtitle = Faker("text")
    author = SubFactory(UserFactory)
    price = 0
    duration = "4 weeks"

    class Meta:
        model = Circle


class CircleEventFactory(DjangoModelFactory):
    circle = SubFactory(CircleFactory)
    start = Faker("future_datetime", tzinfo=datetime.UTC)
    duration_minutes = 60

    class Meta:
        model = CircleEvent
