import pytest
from django.test import Client
from django.urls import reverse

from totem.series.tests.factories import SeriesEventFactory, SeriesFactory
from totem.users.models import User


@pytest.mark.django_db
class TestSeriesAPI:
    def test_list_series(self, client_with_user: tuple[Client, User]):
        """
        Tests the endpoint for listing all published series.
        """
        client, _ = client_with_user
        # Create published series that should appear in the list
        SeriesFactory.create_batch(3, published=True)
        # Create an unpublished series that should NOT appear
        SeriesFactory(published=False)

        url = reverse("mobile-api:list_series")
        response = client.get(url)

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 3
        assert "subtitle" in response_data[0]

    def test_get_series_detail(self, client_with_user: tuple[Client, User]):
        """
        Tests the endpoint for retrieving a single series by its slug.
        """
        client, _ = client_with_user
        series = SeriesFactory(published=True)
        SeriesEventFactory.create_batch(4, series=series)

        url = reverse("mobile-api:get_series", kwargs={"slug": series.slug})
        response = client.get(url)

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["slug"] == series.slug
        assert response_data["title"] == series.title
        assert len(response_data["events"]) == 4
        assert "duration_minutes" in response_data["events"][0]

    def test_get_series_detail_not_found(self, client_with_user: tuple[Client, User]):
        """
        Ensures that a 404 is returned for a non-existent slug.
        """
        client, _ = client_with_user
        url = reverse("mobile-api:get_series", kwargs={"slug": "non-existent-slug"})
        response = client.get(url)
        assert response.status_code == 404

    def test_get_series_detail_unpublished(self, client_with_user: tuple[Client, User]):
        """
        Ensures that an unpublished series is not returned.
        """
        client, _ = client_with_user
        series = SeriesFactory(published=False)
        url = reverse("mobile-api:get_series", kwargs={"slug": series.slug})
        response = client.get(url)
        assert response.status_code == 404
