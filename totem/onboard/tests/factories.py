from collections.abc import Sequence
from typing import Any

from factory import Faker, SubFactory, post_generation
from factory.django import DjangoModelFactory

from totem.onboard.models import OnboardModel
from totem.users.tests.factories import UserFactory
from totem.utils.factories import BaseMetaFactory


class OnboardModelFactory(DjangoModelFactory, metaclass=BaseMetaFactory[OnboardModel]):
    user = SubFactory(UserFactory)
    onboarded = True
    year_born = Faker("random_int", min=1950, max=2005)
    suggestions = Faker("text", max_nb_chars=500)
    hopes = Faker("text", max_nb_chars=500)
    internal_notes = Faker("text", max_nb_chars=1000)
    referral_source = "default"
    referral_other = ""

    @post_generation
    def post_save(self, create: bool, extracted: Sequence[Any], **kwargs):
        if create:
            self.save()  # type: ignore

    class Meta:  # type: ignore
        model = OnboardModel
        django_get_or_create = ["user"]
        skip_postgeneration_save = True
