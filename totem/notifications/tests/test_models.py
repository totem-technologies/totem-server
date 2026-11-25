import pytest
from django.db import IntegrityError, transaction

from totem.notifications.models import FCMDevice
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_fid_uniqueness_and_string_privacy() -> None:
    device = FCMDevice.objects.create(user=UserFactory(), fid="private-identifier")
    assert "private" not in str(device)
    with pytest.raises(IntegrityError), transaction.atomic():
        FCMDevice.objects.create(user=UserFactory(), fid=device.fid)
