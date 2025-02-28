from collections.abc import Sequence
from typing import Any

from django.contrib.auth import get_user_model
from factory import Faker, SubFactory, post_generation
from factory.django import DjangoModelFactory

from totem.users.models import KeeperProfile, User
from totem.utils.factories import BaseMetaFactory


class UserFactory(DjangoModelFactory, metaclass=BaseMetaFactory[User]):
    email = Faker("email")
    name = Faker("name")

    @post_generation
    def password(self, create: bool, extracted: Sequence[Any], **kwargs):
        password = (
            extracted
            if extracted
            else Faker(
                "password",
                length=42,
                special_chars=True,
                digits=True,
                upper_case=True,
                lower_case=True,
            ).evaluate(None, None, extra={"locale": None})
        )
        self.set_password(password)  # type: ignore

    @post_generation
    def post_save(self, create: bool, extracted: Sequence[Any], **kwargs):
        if create:
            self.save()  # type: ignore

    class Meta:  # type: ignore
        model = get_user_model()
        django_get_or_create = ["email"]
        skip_postgeneration_save = True


class KeeperProfileFactory(DjangoModelFactory, metaclass=BaseMetaFactory[KeeperProfile]):
    @post_generation
    def post_save(self, create: bool, extracted: Sequence[Any], **kwargs):
        if create:
            self.save()  # type: ignore

    user = SubFactory(UserFactory)

    class Meta:  # type: ignore
        model = KeeperProfile
        django_get_or_create = ["user"]
        skip_postgeneration_save = True
