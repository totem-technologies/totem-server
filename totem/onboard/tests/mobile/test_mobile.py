import pytest
from django.test import Client
from django.urls import reverse

from totem.onboard.models import OnboardModel
from totem.onboard.tests.factories import OnboardModelFactory
from totem.users.models import User


@pytest.mark.django_db
class TestMobileOnboardAPI:
    def test_get_onboard_authenticated_with_data(self, client_with_user: tuple[Client, User], db):
        """Test retrieving onboard data when user has onboard data."""
        client, user = client_with_user
        url = reverse("mobile-api:onboard")
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["year_born"]
        assert data["hopes"]
        assert data["referral_source"]

    def test_get_onboard_authenticated_no_data(self, client_with_user: tuple[Client, User], db):
        """Test retrieving onboard data when user has no onboard data."""
        client, user = client_with_user
        onboard = OnboardModel.objects.get(user=user)
        onboard.delete()
        url = reverse("mobile-api:onboard")
        response = client.get(url)
        # Should return 404 if no onboard data exists
        assert response.status_code == 404

    def test_get_onboard_unauthenticated(self, client: Client):
        """Test retrieving onboard data when user is not authenticated."""
        url = reverse("mobile-api:onboard")
        response = client.get(url)
        assert response.status_code == 401

    def test_post_onboard_new_user(self, client_with_user: tuple[Client, User], db):
        """Test creating new onboard data for a user."""
        client, user = client_with_user
        url = reverse("mobile-api:onboard")

        payload = {
            "year_born": 1985,
            "hopes": "To learn more about myself",
            "referral_source": "keeper",
            "referral_other": "",
        }

        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200

        # Verify data was saved
        onboard = OnboardModel.objects.get(user=user)
        assert onboard.year_born == 1985
        assert onboard.hopes == "To learn more about myself"
        assert onboard.referral_source == "keeper"

        # Verify response data
        data = response.json()
        assert data["year_born"] == 1985
        assert data["hopes"] == "To learn more about myself"
        assert data["referral_source"] == "keeper"

    def test_post_onboard_with_only_required_fields(self, client_with_user: tuple[Client, User], db):
        """Test creating onboard data with only required fields."""
        client, user = client_with_user
        url = reverse("mobile-api:onboard")

        payload = {"year_born": 2000}

        response = client.post(url, data=payload, content_type="application/json")
        print(response.json())
        assert response.status_code == 200

        # Verify data was saved
        onboard = OnboardModel.objects.get(user=user)
        assert onboard.year_born == 2000

    def test_post_onboard_invalid_year(self, client_with_user: tuple[Client, User], db):
        """Test validation for invalid year_born value."""
        client, user = client_with_user
        url = reverse("mobile-api:onboard")

        # Year out of range
        payload = {"year_born": 2500}

        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 422  # Validation error

        # Ensure year was not recorded
        assert OnboardModel.objects.filter(user=user).get().year_born != 2500

    def test_post_onboard_other_referral(self, client_with_user: tuple[Client, User], db):
        """Test creating onboard data with 'other' referral source."""
        client, user = client_with_user
        url = reverse("mobile-api:onboard")

        payload = {"year_born": 1995, "referral_source": "other", "referral_other": "From a friend's recommendation"}

        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 200

        # Verify data was saved
        onboard = OnboardModel.objects.get(user=user)
        assert onboard.referral_source == "other"
        assert onboard.referral_other == "From a friend's recommendation"

    def test_post_onboard_invalid_referral_source(self, client_with_user: tuple[Client, User], db):
        """Test validation for invalid referral_source value."""
        client, user = client_with_user
        url = reverse("mobile-api:onboard")

        payload = {
            "year_born": 1995,
            "referral_source": "invalid_option",  # Not in choices
        }

        response = client.post(url, data=payload, content_type="application/json")
        print(response.json())
        assert response.status_code == 422  # Validation error

        # Ensure referral is not invalid_option
        assert not OnboardModel.objects.filter(user=user).get().referral_source == "invalid_option"

    def test_post_onboard_unauthenticated(self, client: Client):
        """Test posting onboard data when user is not authenticated."""
        url = reverse("mobile-api:onboard")
        payload = {"year_born": 1990}

        response = client.post(url, data=payload, content_type="application/json")
        assert response.status_code == 401

    def test_post_onboard_existing_user(self, client_with_user: tuple[Client, User], db):
        """Test updating existing onboard data (should create a new record, not update)."""
        client, user = client_with_user

        # Create initial onboard data
        onboard = OnboardModelFactory(user=user, year_born=1980, hopes="Initial hopes")

        url = reverse("mobile-api:onboard")
        payload = {"year_born": 1985, "hopes": "Updated hopes", "referral_source": "dream"}

        response = client.post(url, data=payload, content_type="application/json")
        print(response.json())
        assert response.status_code == 200

        # Should create a new record, not update the existing one
        assert OnboardModel.objects.filter(user=user).count() == 1

        # Get the updated record
        onboard.refresh_from_db()
        assert onboard.year_born == 1985
        assert onboard.hopes == "Updated hopes"
