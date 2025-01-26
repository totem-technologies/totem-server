from factory.django import DjangoModelFactory
from factory import Faker, SubFactory
from datetime import timedelta
from django.utils import timezone

from totem.users.tests.factories import UserFactory
from ..models import BlogPost

class BlogPostFactory(DjangoModelFactory):
    class Meta:
        model = BlogPost

    title = Faker("sentence")
    subtitle = Faker("sentence")
    author = SubFactory(UserFactory)
    content = Faker("paragraph")
    date_published = timezone.now()
    publish = False
