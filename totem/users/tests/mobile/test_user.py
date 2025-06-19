import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from totem.users.models import User
from totem.users.tests.factories import KeeperProfileFactory, UserFactory


@pytest.mark.django_db
class TestMobileUserAPI:
    def test_get_current_user_authenticated(self, client_with_user: tuple[Client, User], db):
        url = reverse("mobile-api:user_current")
        user = client_with_user[1]
        client = client_with_user[0]
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == user.email
        assert data["name"] == user.name
        assert "api_key" in data
        assert data["profile_avatar_type"] == user.profile_avatar_type

    def test_get_current_user_unauthenticated(self, client: Client):
        url = reverse("mobile-api:user_current")
        response = client.get(url)
        assert response.status_code == 401

    def test_update_user_name(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        new_name = "Updated Test Name"
        payload = {"name": new_name}
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.name == new_name
        data = response.json()
        assert data["name"] == new_name

    def test_update_user_email(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        new_email = "newtestemail@example.com"
        payload = {"email": new_email}
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.email == new_email

    def test_update_user_email_conflict(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        UserFactory(email="existing@example.com")
        url = reverse("mobile-api:user_update")
        payload = {"email": "existing@example.com"}
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 422
        data = response.json()
        # Based on the error message in totem.users.mobile_api.py
        assert "not allowed" in str(data)

    def test_update_user_timezone(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        new_timezone = "America/New_York"
        payload = {"timezone": new_timezone}
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert str(user.timezone) == new_timezone

    def test_update_user_invalid_timezone_schema_validation(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        payload = {"timezone": "Invalid/Timezone"}
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 422  # Ninja ValidationError from Pydantic
        data = response.json()
        assert "Invalid timezone" in str(data)

    def test_update_user_newsletter_consent(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        user.newsletter_consent = False
        user.save()
        assert not user.newsletter_consent

        payload = {"newsletter_consent": True}
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.newsletter_consent

    def test_update_user_profile_avatar_type(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        user.profile_avatar_type = User.ProfileChoices.TIEDYE
        user.save()

        payload = {"profile_avatar_type": User.ProfileChoices.IMAGE.value}  # "IM"
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.profile_avatar_type == User.ProfileChoices.IMAGE

    def test_update_user_randomize_avatar_seed(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        new_seed = uuid.uuid4()
        payload = {"profile_avatar_seed": new_seed}
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.profile_avatar_seed == new_seed

    def test_update_user_profile_image(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update_image")
        image_content = b"GIF89a\x01\x00\x01\x00\x00\x00\x00!\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        image = SimpleUploadedFile("test_image.gif", image_content, content_type="image/gif")

        user.profile_avatar_type = User.ProfileChoices.TIEDYE
        user.save()

        response = client.post(url, data={"profile_image": image})  # Multipart

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.profile_image is not None
        assert user.profile_image.name is not None

        assert user.profile_avatar_type == User.ProfileChoices.IMAGE

        data = response.json()
        assert data

    def test_update_user_profile_image_already_image_type(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update_image")
        image_content = b"GIF89a\x01\x00\x01\x00\x00\x00\x00!\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        image = SimpleUploadedFile("test_image_2.gif", image_content, content_type="image/gif")

        user.profile_avatar_type = User.ProfileChoices.IMAGE  # Already image type
        user.save()

        response = client.post(url, data={"profile_image": image})

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.profile_image is not None
        assert user.profile_image.name is not None
        assert user.profile_avatar_type == User.ProfileChoices.IMAGE  # Stays image type

    def test_update_user_profile_image_too_large(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update_image")
        large_content = b"a" * (6 * 1024 * 1024)  # 6MB
        image = SimpleUploadedFile("large_image.jpg", large_content, content_type="image/jpeg")
        response = client.post(url, data={"profile_image": image})
        assert response.status_code == 422
        data = response.json()
        assert data["detail"][0]["profile_image"] == "Image too large. Max 5MB."

    def test_update_user_all_fields_simultaneously(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        original_seed = user.profile_avatar_seed
        user.profile_avatar_type = User.ProfileChoices.TIEDYE  # Start with TIEDYE
        user.newsletter_consent = False
        user.save()

        payload_data = {
            "name": "Mega Update Name",
            "email": "megaupdate@example.com",
            "timezone": "Europe/Paris",
            "newsletter_consent": True,
            "profile_avatar_type": User.ProfileChoices.TIEDYE.value,  # Explicitly set, will be overridden by image
            "profile_avatar_seed": uuid.uuid4(),
        }

        response = client.post(url, data=payload_data, content_type="application/json")
        assert response.status_code == 200

        user.refresh_from_db()
        assert user.name == payload_data["name"]
        assert user.email == payload_data["email"]
        assert str(user.timezone) == payload_data["timezone"]
        assert user.newsletter_consent
        assert user.profile_avatar_type == User.ProfileChoices.TIEDYE
        assert user.profile_avatar_seed != original_seed

        data = response.json()
        assert data["name"] == payload_data["name"]

    def test_update_user_no_payload(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        # Sending an empty JSON payload should not change anything
        response = client.post(url, data={}, content_type="application/json")
        assert response.status_code == 200
        # Ensure user data is unchanged by comparing with a fresh instance
        fresh_user = User.objects.get(pk=user.pk)
        assert user.name == fresh_user.name
        assert user.email == fresh_user.email

    def test_update_user_invalid_profile_avatar_type_value(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_update")
        payload = {"profile_avatar_type": "XX"}  # Invalid value
        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 422
        data = response.json()
        assert "Input should be 'TD' or 'IM'" in data["detail"][0]["msg"]  # Pydantic enum error
        assert "profile_avatar_type" in data["detail"][0]["loc"]

    def test_delete_user(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        user_id = user.pk
        assert User.objects.filter(id=user_id).exists()
        url = reverse("mobile-api:user_delete")
        response = client.delete(url)
        assert response.status_code == 200
        data = response.json()
        assert data is True
        # Verify user is actually deleted
        assert not User.objects.filter(id=user_id).exists()

    def test_public_profile(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        url = reverse("mobile-api:user_profile", args=[user.slug])
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == user.name
        assert "email" not in data
        assert data["profile_avatar_type"] == user.profile_avatar_type.value

    def test_get_keeper_profile_success(self, client_with_user: tuple[Client, User]):
        client = client_with_user[0]
        bio = "Test content"
        keeper_profile = KeeperProfileFactory(username="test_keeper", bio=bio)

        url = reverse("mobile-api:user_keeper_profile", kwargs={"username": "test_keeper"})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["username"] == keeper_profile.username
        assert data["title"] == keeper_profile.title
        assert data["bio"] == keeper_profile.bio
        assert data["location"] == keeper_profile.location

        assert data["user"]["name"] == keeper_profile.user.name

        assert "circle_count" in data
        assert data["circle_count"] == 0

        assert "bio_html" in data
        assert bio in data["bio_html"]
        assert data["bio_html"] == "\n<p>Test content</p>"

        assert "email" not in data["user"]
        assert "api_key" not in data["user"]

    def test_get_keeper_profile_not_found(self, client_with_user: tuple[Client, User]):
        """
        Tests that a 404 is returned for a non-existent keeper username.
        """
        client = client_with_user[0]
        url = reverse("mobile-api:user_keeper_profile", kwargs={"username": "ghost_keeper"})
        response = client.get(url)
        assert response.status_code == 404
