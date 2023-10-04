import datetime

from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from totem.users.tests.factories import UserFactory
from totem.utils.factories import BaseMetaFactory

from ..models import Circle, CircleEvent


class CircleFactory(DjangoModelFactory, metaclass=BaseMetaFactory[Circle]):
    title = Faker("name")
    subtitle = Faker("text")
    author = SubFactory(UserFactory)
    price = 0
    recurring = "4 weeks"
    published = True

    class Meta:
        model = Circle


class CircleEventFactory(DjangoModelFactory, metaclass=BaseMetaFactory[CircleEvent]):
    circle = SubFactory(CircleFactory)
    start = Faker("future_datetime", tzinfo=datetime.UTC)
    meeting_url = "https://example.com"
    duration_minutes = 60

    class Meta:
        model = CircleEvent
