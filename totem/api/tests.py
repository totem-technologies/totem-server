from django.test import Client
from django.urls import reverse

from totem.api.api import AvatarUpdate
from totem.users.schemas import ProfileAvatarTypeEnum
from totem.users.tests.factories import UserFactory


def test_avatar_update(client: Client, db):
    user = UserFactory()
    client.force_login(user)
    response = client.post(
        reverse("api-1:user_avatar_update"),
        data=AvatarUpdate(avatar_type=ProfileAvatarTypeEnum.IMAGE, update_avatar_seed=False).model_dump(),
        content_type="application/json",
    )
    user.refresh_from_db()
    assert response.status_code == 200
    assert user.profile_avatar_type == ProfileAvatarTypeEnum.IMAGE

    response = client.post(
        reverse("api-1:user_avatar_update"),
        data=AvatarUpdate(avatar_type=ProfileAvatarTypeEnum.TIEDYE, update_avatar_seed=False).model_dump(),
        content_type="application/json",
    )
    user.refresh_from_db()
    assert response.status_code == 200
    assert user.profile_avatar_type == ProfileAvatarTypeEnum.TIEDYE
    seed = user.profile_avatar_seed

    response = client.post(
        reverse("api-1:user_avatar_update"),
        data=AvatarUpdate(avatar_type=None, update_avatar_seed=True).model_dump(),
        content_type="application/json",
    )
    user.refresh_from_db()
    assert response.status_code == 200
    assert user.profile_avatar_type == ProfileAvatarTypeEnum.TIEDYE
    assert user.profile_avatar_seed != seed
