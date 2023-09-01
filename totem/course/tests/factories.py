from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from totem.course.models import CoursePage
from totem.users.tests.factories import UserFactory


class CoursePageFactory(DjangoModelFactory):
    title = Faker("name")
    created_by = SubFactory(UserFactory)
    content = Faker("text")

    class Meta:
        model = CoursePage
