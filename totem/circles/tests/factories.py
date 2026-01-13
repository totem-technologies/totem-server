import datetime

from factory import Faker, SubFactory, post_generation
from factory.django import DjangoModelFactory

from totem.users.tests.factories import UserFactory
from totem.utils.factories import BaseMetaFactory

from ..models import Session, Space, SpaceCategory


class SpaceFactory(DjangoModelFactory, metaclass=BaseMetaFactory[Space]):
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

    class Meta:  # type: ignore
        model = Space
        skip_postgeneration_save = True


class SessionFactory(DjangoModelFactory, metaclass=BaseMetaFactory[Session]):
    # Use actual field name 'circle' but keep 'space' as alias for backwards compat
    circle = SubFactory(SpaceFactory)
    start = Faker("future_datetime", tzinfo=datetime.UTC)
    meeting_url = "https://example.com"
    duration_minutes = 60

    class Meta:  # type: ignore
        model = Session


class SpaceCategoryFactory(DjangoModelFactory, metaclass=BaseMetaFactory[SpaceCategory]):
    name = Faker("name")
    slug = Faker("slug")

    class Meta:  # type: ignore
        model = SpaceCategory


SpaceFactory = SpaceFactory
SessionFactory = SessionFactory
SpaceCategoryFactory = SpaceCategoryFactory
