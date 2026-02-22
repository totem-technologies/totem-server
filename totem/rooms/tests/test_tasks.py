from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from totem.rooms.models import Room
from totem.rooms.schemas import EndReason, RoomStatus, TurnState
from totem.rooms.tasks import end_sessions_without_keeper
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.tests.factories import UserFactory


def _make_active_session_without_keeper():
    """Create a session that started 10 min ago with a keeper who hasn't joined."""
    keeper = UserFactory()
    space = SpaceFactory(author=keeper)
    session = SessionFactory(
        space=space,
        start=timezone.now() - timedelta(minutes=10),
    )
    return session, keeper


@pytest.mark.django_db
class TestEndSessionsWithoutKeeper:
    def test_ends_room_when_keeper_absent(self):
        session, keeper = _make_active_session_without_keeper()
        room = Room.objects.get_or_create_for_session(session)

        with (
            patch("totem.rooms.tasks.get_connected_participants", return_value=set()),
            patch("totem.rooms.tasks.publish_state"),
        ):
            count = end_sessions_without_keeper()

        assert count == 1
        room.refresh_from_db()
        assert room.status == RoomStatus.ENDED
        assert room.turn_state == TurnState.IDLE
        assert room.current_speaker is None
        assert room.next_speaker is None
        assert room.end_reason == EndReason.KEEPER_ABSENT

    def test_publishes_state_to_livekit_after_ending_room(self):
        session, keeper = _make_active_session_without_keeper()
        Room.objects.get_or_create_for_session(session)

        with (
            patch("totem.rooms.tasks.get_connected_participants", return_value=set()),
            patch("totem.rooms.tasks.publish_state") as mock_publish,
        ):
            end_sessions_without_keeper()

        mock_publish.assert_called_once()
        session_slug_arg, room_state = mock_publish.call_args[0]
        assert session_slug_arg == session.slug
        assert room_state.status == RoomStatus.ENDED

    def test_no_room_exists_does_not_crash(self):
        session, keeper = _make_active_session_without_keeper()
        # No Room created for this session

        with (
            patch("totem.rooms.tasks.get_connected_participants", return_value=set()),
            patch("totem.rooms.tasks.publish_state"),
        ):
            count = end_sessions_without_keeper()

        assert count == 1  # session still ended, no crash

    def test_already_ended_room_is_not_modified(self):
        session, keeper = _make_active_session_without_keeper()
        room = Room.objects.get_or_create_for_session(session)
        room.status = RoomStatus.ENDED
        room.end_reason = EndReason.KEEPER_ENDED
        room.state_version = 5
        room.save()

        with (
            patch("totem.rooms.tasks.get_connected_participants", return_value=set()),
            patch("totem.rooms.tasks.publish_state") as mock_publish,
        ):
            end_sessions_without_keeper()

        room.refresh_from_db()
        assert room.end_reason == EndReason.KEEPER_ENDED  # unchanged
        assert room.state_version == 5  # unchanged
        mock_publish.assert_not_called()

    def test_publish_state_failure_does_not_abort_task(self):
        session1, _ = _make_active_session_without_keeper()
        session2, _ = _make_active_session_without_keeper()
        Room.objects.get_or_create_for_session(session1)
        Room.objects.get_or_create_for_session(session2)

        call_count = 0

        def flaky_publish(slug, state):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("LiveKit down")

        with (
            patch("totem.rooms.tasks.get_connected_participants", return_value=set()),
            patch("totem.rooms.tasks.publish_state", side_effect=flaky_publish),
        ):
            count = end_sessions_without_keeper()

        assert count == 2  # both sessions ended despite first publish failure
