import uuid

import factory
from django.utils import timezone

from totem.notifications.models import FCMDevice
from totem.users.tests.factories import UserFactory


class FCMDeviceFactory(factory.django.DjangoModelFactory):
    """Factory for creating FCMDevice instances."""

    class Meta:
        model = FCMDevice

    user = factory.SubFactory(UserFactory)
    token = factory.LazyFunction(lambda: f"fcm_token_{uuid.uuid4().hex[:140]}")
    active = True
    last_used = factory.LazyFunction(timezone.now)
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)
