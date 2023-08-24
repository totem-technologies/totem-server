import pytz
from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from totem.users.tests.factories import UserFactory

from ..models import Circle


class CircleFactory(DjangoModelFactory):
    title = Faker("name")
    subtitle = Faker("text")
    author = SubFactory(UserFactory)
    price = "Free"
    start = Faker("future_datetime", tzinfo=pytz.UTC)
    duration = "1 hour"
    recurring = "Never"
    google_url = Faker("url")

    class Meta:
        model = Circle
