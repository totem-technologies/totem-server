import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from totem.users.tests.factories import UserFactory

from .factories import SessionFactory


class TestSessionAdmin:
    def test_change_page_shows_attendee_emails(self, admin_client):
        session = SessionFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        session.attendees.add(user1, user2)
        url = reverse("admin:spaces_session_change", kwargs={"object_id": session.pk})
        response = admin_client.get(url)
        assert response.status_code == 200
        assert user1.email in response.content.decode()
        assert user2.email in response.content.decode()

    def test_change_page_links_to_participants(self, admin_client):
        session = SessionFactory()
        url = reverse("admin:spaces_session_change", kwargs={"object_id": session.pk})
        response = admin_client.get(url)
        assert reverse("admin:spaces_session_participants", args=[session.pk]) in response.content.decode()

    def test_add_page_renders(self, admin_client):
        # The participants link can't be built before the session has a pk.
        assert admin_client.get(reverse("admin:spaces_session_add")).status_code == 200


@pytest.mark.django_db
class TestSessionParticipantsView:
    def test_shows_participant_details(self, admin_client):
        session = SessionFactory()
        user = UserFactory(name="Claire")
        session.attendees.add(user)
        past = SessionFactory(start=timezone.now() - datetime.timedelta(days=7))
        past.attendees.add(user)
        past.joined.add(user)

        url = reverse("admin:spaces_session_participants", args=[session.pk])
        response = admin_client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Claire" in content
        assert user.email in content
        assert "100%" in content
        assert "1/1" in content

    def test_first_time_badge(self, admin_client):
        session = SessionFactory()
        session.attendees.add(UserFactory(name="Nate"))

        url = reverse("admin:spaces_session_participants", args=[session.pk])
        content = admin_client.get(url).content.decode()

        assert "First time" in content
        # Nobody with an empty record should be shown a meaningless "0% · 0/0".
        assert "No history" in content
        assert "0/0" not in content

    def test_missing_session_is_404(self, admin_client):
        url = reverse("admin:spaces_session_participants", args=[123456])
        assert admin_client.get(url).status_code == 404

    def test_staff_without_session_permission_is_404(self, client):
        session = SessionFactory()
        client.force_login(UserFactory(is_staff=True))
        url = reverse("admin:spaces_session_participants", args=[session.pk])
        assert client.get(url).status_code == 404

    def test_requires_staff(self, client):
        session = SessionFactory()
        client.force_login(UserFactory())
        url = reverse("admin:spaces_session_participants", args=[session.pk])
        response = client.get(url)
        assert response.status_code == 302
        assert "/admin/login/" in response.url
