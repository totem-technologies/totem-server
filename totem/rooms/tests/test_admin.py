from django.urls import reverse

from totem.rooms.models import Room
from totem.spaces.tests.factories import SessionFactory


class TestRoomAdmin:
    def test_add_page_is_disabled(self, admin_client):
        response = admin_client.get(reverse("admin:rooms_room_add"))

        assert response.status_code == 403

    def test_change_page_remains_available(self, admin_client):
        room = Room.objects.get_or_create_for_session(SessionFactory())
        url = reverse("admin:rooms_room_change", args=[room.pk])

        assert admin_client.get(url).status_code == 200
