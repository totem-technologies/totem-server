from django.utils import timezone
from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from totem.users.tests.factories import UserFactory

from ..models import BlogPost


class BlogPostFactory(DjangoModelFactory):
    class Meta:  # type: ignore
        model = BlogPost

    title = Faker("sentence")
    summary = Faker("sentence")
    subtitle = Faker("sentence")
    author = SubFactory(UserFactory)
    content = Faker("paragraph")
    date_published = timezone.now()
    publish = False
