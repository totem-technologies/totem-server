import pytest
from django.test import Client
from django.urls import reverse

from totem.api.auth import generate_jwt_token
from totem.notifications.models import FCMDevice
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_unregister_fid_is_idempotent_and_scoped_to_owner(client: Client) -> None:
    owner, other = UserFactory(), UserFactory()
    device = FCMDevice.objects.create(user=owner, fid="some/fid", active=False)
    url = reverse("mobile-api:unregister_fcm_fid", kwargs={"fid": device.fid})
    assert client.delete(url).status_code == 401
    assert client.delete(url, HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(other)}").status_code == 204
    assert FCMDevice.objects.filter(pk=device.pk).exists()
    for _ in range(2):
        assert client.delete(url, HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(owner)}").status_code == 204
    assert not FCMDevice.objects.filter(pk=device.pk).exists()
