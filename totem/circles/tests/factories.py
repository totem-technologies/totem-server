import datetime

from factory import Faker, SubFactory, post_generation
from factory.django import DjangoModelFactory

from totem.users.tests.factories import UserFactory
from totem.utils.factories import BaseMetaFactory

from ..models import Circle, CircleCategory, CircleEvent


class CircleFactory(DjangoModelFactory, metaclass=BaseMetaFactory[Circle]):
    title = Faker("name")
    subtitle = Faker("text")
    author = SubFactory(UserFactory)
    price = 0
    recurring = "4 weeks"
    published = True

    @post_generation
    def categories(self, create, extracted, **kwargs):
        if not create or not extracted:
            return
        self.categories.add(*extracted)  # type: ignore
        self.save()  # type: ignore

    class Meta:
        model = Circle
        skip_postgeneration_save = True


class CircleEventFactory(DjangoModelFactory, metaclass=BaseMetaFactory[CircleEvent]):
    circle = SubFactory(CircleFactory)
    start = Faker("future_datetime", tzinfo=datetime.UTC)
    meeting_url = "https://example.com"
    duration_minutes = 60

    class Meta:
        model = CircleEvent


class CircleCategoryFactory(DjangoModelFactory, metaclass=BaseMetaFactory[CircleCategory]):
    name = Faker("name")
    slug = Faker("slug")

    class Meta:
        model = CircleCategory
