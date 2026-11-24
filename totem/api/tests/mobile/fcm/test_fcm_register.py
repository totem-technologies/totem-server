from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client
from django.urls import reverse

from totem.api.auth import generate_jwt_token
from totem.notifications.models import FCMDevice
from totem.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_register_fid_reassigns_and_reactivates(client: Client) -> None:
    user = UserFactory()
    other = UserFactory()
    device = FCMDevice.objects.create(user=other, fid="opaque+/=fid", active=False)
    response = client.post(
        reverse("mobile-api:register_fcm_fid"),
        {"fid": device.fid},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(user)}",
    )
    assert response.status_code == 201
    assert response.json()["fid"] == device.fid
    device.refresh_from_db()
    assert device.user == user
    assert device.active
    assert FCMDevice.objects.filter(fid=device.fid).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("fid", ["", "a" * 513, "a b", "a\tb", "a\nb", "a\u00a0b", "a\x00b", "a\x7fb", "a\x80b"])
def test_register_invalid_fid(client: Client, fid: str) -> None:
    response = client.post(
        reverse("mobile-api:register_fcm_fid"),
        {"fid": fid},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(UserFactory())}",
    )
    assert response.status_code == 422
    assert not FCMDevice.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("fid", ["short", "a" * 23, "a" * 512, "abc+/=é"])
def test_register_fid_without_assuming_format(client: Client, fid: str) -> None:
    response = client.post(
        reverse("mobile-api:register_fcm_fid"),
        {"fid": fid},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(UserFactory())}",
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_register_rejects_legacy_payload_and_requires_authentication(client: Client) -> None:
    url = reverse("mobile-api:register_fcm_fid")
    assert client.post(url, {"fid": "fid"}, content_type="application/json").status_code == 401
    response = client.post(
        url,
        {"token": "legacy-token"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(UserFactory())}",
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_fid_is_unique_across_users() -> None:
    FCMDevice.objects.create(user=UserFactory(), fid="same")
    with pytest.raises(IntegrityError), transaction.atomic():
        FCMDevice.objects.create(user=UserFactory(), fid="same")


@pytest.mark.django_db(transaction=True)
def test_concurrent_registration_reassigns_one_device() -> None:
    tokens = [generate_jwt_token(UserFactory()), generate_jwt_token(UserFactory())]
    barrier = Barrier(2)

    def register(token: str) -> int:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return (
                Client()
                .post(
                    reverse("mobile-api:register_fcm_fid"),
                    {"fid": "same-fid"},
                    content_type="application/json",
                    HTTP_AUTHORIZATION=f"Bearer {token}",
                )
                .status_code
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(register, tokens)) == [201, 201]
    assert FCMDevice.objects.filter(fid="same-fid").count() == 1
