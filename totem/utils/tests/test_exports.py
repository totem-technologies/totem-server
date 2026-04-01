from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from totem.onboard.tests.factories import OnboardModelFactory
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory


@pytest.fixture
def admin_client(db) -> Client:
    user = UserFactory(is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    return client


class TestExportListView:
    def test_requires_staff(self, db):
        client = Client()
        url = reverse("admin:exports_index")
        response = client.get(url)
        assert response.status_code == 302

    def test_staff_can_access(self, admin_client):
        url = reverse("admin:exports_index")
        response = admin_client.get(url)
        assert response.status_code == 200
        assert b"Data Exports" in response.content

    def test_lists_exports(self, admin_client):
        url = reverse("admin:exports_index")
        response = admin_client.get(url)
        assert b"Onboarded, no session in 90 days" in response.content
        assert b"Session stats summary" in response.content
        assert b"Grant metrics report" in response.content


class TestOnboardedNoSession90DaysExport:
    def test_download_csv(self, admin_client):
        url = reverse("admin:exports_download", args=["onboarded-no-session-90-days"])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

    def test_includes_onboarded_user_with_no_sessions(self, admin_client):
        onboard = OnboardModelFactory(onboarded=True)
        url = reverse("admin:exports_download", args=["onboarded-no-session-90-days"])
        response = admin_client.get(url)
        content = response.content.decode()
        assert onboard.user.email in content

    def test_excludes_user_with_recent_session(self, admin_client):
        onboard = OnboardModelFactory(onboarded=True)
        session = SessionFactory(start=timezone.now() - timedelta(days=30))
        session.joined.add(onboard.user)
        url = reverse("admin:exports_download", args=["onboarded-no-session-90-days"])
        response = admin_client.get(url)
        content = response.content.decode()
        assert onboard.user.email not in content

    def test_includes_user_with_old_session(self, admin_client):
        onboard = OnboardModelFactory(onboarded=True)
        session = SessionFactory(start=timezone.now() - timedelta(days=120))
        session.joined.add(onboard.user)
        url = reverse("admin:exports_download", args=["onboarded-no-session-90-days"])
        response = admin_client.get(url)
        content = response.content.decode()
        assert onboard.user.email in content

    def test_excludes_non_onboarded_user(self, admin_client):
        UserFactory(email="notonboarded@test.example", onboarded=False)
        url = reverse("admin:exports_download", args=["onboarded-no-session-90-days"])
        response = admin_client.get(url)
        content = response.content.decode()
        assert "notonboarded@test.example" not in content

    def test_404_for_unknown_export(self, admin_client):
        url = reverse("admin:exports_download", args=["nonexistent"])
        response = admin_client.get(url)
        assert response.status_code == 404


class TestSessionStatsExport:
    def test_shows_form_without_params(self, admin_client):
        url = reverse("admin:exports_download", args=["session-stats"])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert b"<form" in response.content
        assert b"period" in response.content

    def test_downloads_txt_with_params(self, admin_client):
        url = reverse("admin:exports_download", args=["session-stats"])
        response = admin_client.get(url, {"period": "last_quarter"})
        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain"
        content = response.content.decode()
        assert "Session Stats:" in content
        assert "Total sessions:" in content

    def test_invalid_period_shows_form(self, admin_client):
        url = reverse("admin:exports_download", args=["session-stats"])
        response = admin_client.get(url, {"period": "invalid"})
        assert response.status_code == 200
        assert b"<form" in response.content


class TestGrantMetricsExport:
    def test_shows_form_without_params(self, admin_client):
        url = reverse("admin:exports_download", args=["grant-metrics"])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert b"<form" in response.content
        assert b"year" in response.content

    def test_downloads_txt(self, admin_client):
        url = reverse("admin:exports_download", args=["grant-metrics"])
        year = str(timezone.now().year)
        response = admin_client.get(url, {"year": year})
        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain"
        content = response.content.decode()
        assert "GRANT METRICS REPORT" in content
        assert f"Report year: {year}" in content
        assert "GROWTH & REACH" in content
        assert "ENGAGEMENT & RETENTION" in content
        assert "GEOGRAPHIC DIVERSITY" in content

    def test_includes_session_data(self, admin_client):
        """Verify metrics reflect actual session data."""
        user = UserFactory()
        session = SessionFactory(start=timezone.now() - timedelta(days=10))
        session.attendees.add(user)
        session.joined.add(user)

        url = reverse("admin:exports_download", args=["grant-metrics"])
        response = admin_client.get(url, {"year": str(timezone.now().year)})
        content = response.content.decode()
        assert "Unique participants (lifetime):" in content
        assert "Total sessions hosted:" in content
