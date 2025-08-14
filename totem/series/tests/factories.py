import factory
from factory.django import DjangoModelFactory

from totem.users.tests.factories import UserFactory

from ..models import Series, SeriesCategory, SeriesEvent


class SeriesCategoryFactory(DjangoModelFactory):
    class Meta:
        model = SeriesCategory

    name = factory.Faker("word")
    slug = factory.Faker("slug")


class SeriesFactory(DjangoModelFactory):
    class Meta:
        model = Series

    title = factory.Faker("sentence")
    subtitle = factory.Faker("sentence")
    author = factory.SubFactory(UserFactory)
    published = True

    @factory.post_generation
    def categories(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for category in extracted:
                self.categories.add(category)


class SeriesEventFactory(DjangoModelFactory):
    class Meta:
        model = SeriesEvent

    series = factory.SubFactory(SeriesFactory)
    title = factory.Faker("sentence")
    order = factory.Sequence(lambda n: n + 1)
    published = True
