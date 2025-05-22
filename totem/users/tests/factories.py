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
        self.set_unusable_password()

    @post_generation
    def post_save(self, create: bool, extracted: Sequence[Any], **kwargs):
        if create:
            self.save()  # type: ignore

    @post_generation
    def onboarded(self, create: bool, extracted: bool | None, **kwargs):
        if create:
            # Import here to avoid circular imports
            from totem.onboard.tests.factories import OnboardModelFactory

            # Only skip creating the onboard profile if explicitly set to False
            if extracted is not False:
                OnboardModelFactory(user=self, onboarded=True)

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
