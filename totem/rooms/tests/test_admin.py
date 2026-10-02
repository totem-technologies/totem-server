from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import connection, connections
from django.test import RequestFactory
from django.urls import reverse

from totem.rooms.admin import RoomAdmin
from totem.rooms.models import Room
from totem.rooms.schemas import EmptyRoomEvent, EndReason, RoomStatus
from totem.rooms.state_machine import apply_event
from totem.spaces.tests.factories import SessionFactory


class TestRoomAdmin:
    def test_add_page_is_disabled(self, admin_client):
        response = admin_client.get(reverse("admin:rooms_room_add"))

        assert response.status_code == 403

    def test_change_page_remains_available(self, admin_client):
        room = Room.objects.get_or_create_for_session(SessionFactory())
        url = reverse("admin:rooms_room_change", args=[room.pk])

        assert admin_client.get(url).status_code == 200

    @pytest.mark.django_db(transaction=True)
    def test_admin_can_save_while_room_event_holds_session_lock(self) -> None:
        session = SessionFactory()
        room = Room.objects.get_or_create_for_session(session)
        session_locked = Event()
        admin_lock_requested = Event()

        def run_event() -> None:
            def coordinate_event(
                execute: Callable[..., Any], sql: str, params: Any, many: bool, context: dict[str, Any]
            ) -> Any:
                if '"rooms_room"' in sql and "FOR UPDATE" in sql:
                    # The event holds Session; let the admin reach its own Session lock.
                    session_locked.set()
                    assert admin_lock_requested.wait(10), "Admin did not request the Session lock"
                return execute(sql, params, many, context)

            try:
                with connection.execute_wrapper(coordinate_event):
                    apply_event(session.slug, room.keeper, EmptyRoomEvent(), None, set())
            finally:
                connections.close_all()

        def run_admin() -> None:
            def coordinate_admin(
                execute: Callable[..., Any], sql: str, params: Any, many: bool, context: dict[str, Any]
            ) -> Any:
                if '"spaces_session"' in sql and "FOR UPDATE" in sql:
                    admin_lock_requested.set()
                return execute(sql, params, many, context)

            try:
                assert session_locked.wait(10), "Room event did not acquire the Session lock"
                obj = Room.objects.get(pk=room.pk)
                obj.status = RoomStatus.ENDED
                obj.end_reason = EndReason.KEEPER_ENDED
                request = RequestFactory().post("/")
                request.user = session.space.author
                with connection.execute_wrapper(coordinate_admin):
                    RoomAdmin(Room, AdminSite()).save_model(request, obj, None, True)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            event_future = pool.submit(run_event)
            admin_future = pool.submit(run_admin)
            event_future.result(timeout=20)
            admin_future.result(timeout=20)

        room.refresh_from_db()
        session.refresh_from_db()
        assert room.status == RoomStatus.ENDED
        assert session.ended_at is not None
