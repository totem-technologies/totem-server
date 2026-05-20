from unittest.mock import Mock

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.utils import timezone

from totem.rooms.admin import RoomAdmin
from totem.rooms.models import Room
from totem.rooms.schemas import RoomStatus
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.tests.factories import UserFactory


@pytest.fixture
def admin_user(db):
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def admin_site():
    return AdminSite()


@pytest.fixture
def room_admin(admin_site):
    return RoomAdmin(Room, admin_site)


@pytest.fixture
def request_factory():
    return RequestFactory()


class TestRoomAdmin:
    def test_end_rooms_action_ends_selected_rooms(self, db, room_admin, request_factory, admin_user):
        """Test that the end_rooms action properly ends selected rooms and syncs session.ended_at"""
        room_admin.message_user = Mock()

        space = SpaceFactory()
        session1 = SessionFactory(space=space)
        session2 = SessionFactory(space=space)
        room1 = Room.objects.create(session=session1, status=RoomStatus.ACTIVE)
        room2 = Room.objects.create(session=session2, status=RoomStatus.ACTIVE)

        request = request_factory.post("/")
        request.user = admin_user

        queryset = Room.objects.filter(pk__in=[room1.pk, room2.pk])

        room_admin.end_rooms(request, queryset)

        room1.refresh_from_db()
        room2.refresh_from_db()
        session1.refresh_from_db()
        session2.refresh_from_db()

        assert room1.status == RoomStatus.ENDED
        assert room2.status == RoomStatus.ENDED

        assert session1.ended_at is not None
        assert session2.ended_at is not None

        # Assert ended_at is recent (within last minute)
        now = timezone.now()
        assert (now - session1.ended_at).total_seconds() < 60
        assert (now - session2.ended_at).total_seconds() < 60

        # Assert message_user was called
        room_admin.message_user.assert_called_once_with(request, "Ended 2 room(s).")

    def test_end_rooms_action_skips_already_ended_rooms(self, db, room_admin, request_factory, admin_user):
        """Test that the end_rooms action skips rooms that are already ended"""
        room_admin.message_user = Mock()

        space = SpaceFactory()
        session1 = SessionFactory(space=space)
        session2 = SessionFactory(space=space, ended_at=timezone.now())
        room1 = Room.objects.create(session=session1, status=RoomStatus.ACTIVE)
        room2 = Room.objects.create(session=session2, status=RoomStatus.ENDED)

        request = request_factory.post("/")
        request.user = admin_user

        queryset = Room.objects.filter(pk__in=[room1.pk, room2.pk])

        room_admin.end_rooms(request, queryset)

        room1.refresh_from_db()
        room2.refresh_from_db()
        session1.refresh_from_db()
        session2.refresh_from_db()

        assert room1.status == RoomStatus.ENDED
        assert room2.status == RoomStatus.ENDED

        assert session1.ended_at is not None
        assert session2.ended_at is not None

        # Assert message_user was called with count of actually ended rooms
        room_admin.message_user.assert_called_once_with(request, "Ended 1 room(s).")

    def test_save_model_syncs_session_ended_at_when_room_ended(self, db, room_admin, request_factory, admin_user):
        """Test that save_model properly syncs session.ended_at when room status changes to ENDED"""
        space = SpaceFactory()
        session = SessionFactory(space=space)
        room = Room.objects.create(session=session, status=RoomStatus.ACTIVE)

        assert session.ended_at is None

        request = request_factory.post("/")
        request.user = admin_user

        room.status = RoomStatus.ENDED
        room_admin.save_model(request, room, None, True)

        session.refresh_from_db()

        assert session.ended_at is not None

    def test_save_model_clears_session_ended_at_when_room_not_ended(self, db, room_admin, request_factory, admin_user):
        """Test that save_model clears session.ended_at when room status changes from ENDED to something else"""
        space = SpaceFactory()
        session = SessionFactory(space=space, ended_at=timezone.now())
        room = Room.objects.create(session=session, status=RoomStatus.ENDED)

        request = request_factory.post("/")
        request.user = admin_user

        room.status = RoomStatus.ACTIVE
        room_admin.save_model(request, room, None, True)

        session.refresh_from_db()

        assert session.ended_at is None
