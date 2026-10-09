import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


class TestUserAdmin:
    def test_changelist(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_search(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url, data={"q": "test"})
        assert response.status_code == 200

    def test_add(self, admin_client):
        url = reverse("admin:users_user_add")
        response = admin_client.get(url)
        assert response.status_code == 200

        response = admin_client.post(
            url,
            data={
                "email": "new-admin@totem.org",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "My_R@ndom-P@ssw0rd",
            },
        )
        assert response.status_code == 302
        assert User.objects.filter(email="new-admin@totem.org").exists()

    def test_view_user(self, admin_client):
        user = User.objects.get(email="admin@example.com")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_changelist_can_add_user(self, admin_client):
        response = admin_client.get(reverse("admin:users_user_changelist"))
        assert reverse("admin:users_user_add") in response.content.decode()


class TestUserRelatedWidgets:
    def test_no_add_user_button_on_related_fields(self, admin_client):
        response = admin_client.get(reverse("admin:spaces_session_add"))
        content = response.content.decode()
        assert response.status_code == 200
        assert 'id="id_attendees"' in content
        assert reverse("admin:users_user_add") not in content


@pytest.mark.django_db
class TestUserSessionHistoryView:
    def test_change_page_links_to_session_history(self, admin_client):
        user = UserFactory()
        response = admin_client.get(reverse("admin:users_user_change", args=[user.pk]))
        assert reverse("admin:users_user_sessions", args=[user.pk]) in response.content.decode()

    def test_shows_sessions_keepers_and_status(self, admin_client):
        user = UserFactory()
        keeper = UserFactory(name="Keeper Kim")
        session = SessionFactory(
            space=SpaceFactory(author=keeper, title="Grief Circle"),
            start=timezone.now() - datetime.timedelta(days=7),
        )
        session.attendees.add(user)

        response = admin_client.get(reverse("admin:users_user_sessions", args=[user.pk]))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Grief Circle" in content
        assert "Keeper Kim" in content
        assert "No-show" in content
        assert reverse("admin:spaces_session_change", args=[session.pk]) in content

    def test_empty_history(self, admin_client):
        user = UserFactory()
        response = admin_client.get(reverse("admin:users_user_sessions", args=[user.pk]))
        assert "No sessions yet." in response.content.decode()

    def test_missing_user_is_404(self, admin_client):
        assert admin_client.get(reverse("admin:users_user_sessions", args=[123456])).status_code == 404

    def test_staff_without_user_permission_is_404(self, client):
        client.force_login(UserFactory(is_staff=True))
        user = UserFactory()
        assert client.get(reverse("admin:users_user_sessions", args=[user.pk])).status_code == 404

    def test_participants_page_links_to_session_history(self, admin_client):
        session = SessionFactory()
        user = UserFactory()
        session.attendees.add(user)
        response = admin_client.get(reverse("admin:spaces_session_participants", args=[session.pk]))
        assert reverse("admin:users_user_sessions", args=[user.pk]) in response.content.decode()
