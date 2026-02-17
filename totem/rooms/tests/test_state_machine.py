import pytest

from totem.rooms.models import Room
from totem.rooms.schemas import (
    AcceptStickEvent,
    EndReason,
    EndRoomEvent,
    ErrorCode,
    PassStickEvent,
    ReorderEvent,
    RoomStatus,
    SkipParticipantEvent,
    StartRoomEvent,
    TransitionError,
    TurnState,
)
from totem.rooms.state_machine import _next_in_order, _reconcile_talking_order, apply_event
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory

# ---------------------------------------------------------------------------
# Pure helper: _next_in_order
# ---------------------------------------------------------------------------


class TestNextInOrder:
    def test_returns_next_connected(self):
        order = ["a", "b", "c"]
        assert _next_in_order(order, "a", {"a", "b", "c"}) == "b"

    def test_wraps_around(self):
        order = ["a", "b", "c"]
        assert _next_in_order(order, "c", {"a", "b", "c"}) == "a"

    def test_skips_disconnected(self):
        order = ["a", "b", "c"]
        assert _next_in_order(order, "a", {"a", "c"}) == "c"

    def test_returns_self_if_only_connected(self):
        order = ["a", "b", "c"]
        assert _next_in_order(order, "a", {"a"}) == "a"

    def test_returns_none_if_nobody_connected(self):
        order = ["a", "b", "c"]
        assert _next_in_order(order, "a", set()) is None

    def test_returns_none_if_after_not_in_order(self):
        order = ["a", "b", "c"]
        assert _next_in_order(order, "x", {"a", "b", "c"}) is None

    def test_empty_order(self):
        assert _next_in_order([], "a", {"a"}) is None

    def test_two_people_alternates(self):
        order = ["a", "b"]
        assert _next_in_order(order, "a", {"a", "b"}) == "b"
        assert _next_in_order(order, "b", {"a", "b"}) == "a"


# ---------------------------------------------------------------------------
# Reconciliation: _reconcile_talking_order
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReconcileTalkingOrder:
    def _make_room(self, keeper_slug: str, talking_order: list[str], **kwargs) -> Room:
        """Create a Room with the given state, using a real Session."""
        session = SessionFactory()
        room = Room(
            session=session,
            keeper=keeper_slug,
            talking_order=talking_order,
            **kwargs,
        )
        room.save()
        return room

    def test_preserves_existing_order(self):
        room = self._make_room("a", ["a", "b", "c"])
        _reconcile_talking_order(room, {"a", "b", "c"})
        assert room.talking_order == ["a", "b", "c"]

    def test_keeps_disconnected_in_order(self):
        room = self._make_room("a", ["a", "b", "c"])
        _reconcile_talking_order(room, {"a", "c"})
        assert room.talking_order == ["a", "b", "c"]

    def test_adds_new_at_end(self):
        room = self._make_room("a", ["a", "b"])
        _reconcile_talking_order(room, {"a", "b", "d"})
        assert room.talking_order[:2] == ["a", "b"]
        assert "d" in room.talking_order

    def test_keeper_first_when_connected(self):
        room = self._make_room("b", ["a", "c"])
        _reconcile_talking_order(room, {"a", "b", "c"})
        assert room.talking_order[0] == "b"

    def test_empty_connected_preserves_order(self):
        room = self._make_room("a", ["a", "b", "c"])
        _reconcile_talking_order(room, set())
        assert room.talking_order == ["a", "b", "c"]

    def test_fixes_current_speaker_on_disconnect(self):
        room = self._make_room(
            "a",
            ["a", "b", "c"],
            current_speaker="b",
            turn_state=TurnState.SPEAKING,
            status=RoomStatus.ACTIVE,
        )
        _reconcile_talking_order(room, {"a", "c"})
        assert room.current_speaker == "a"

    def test_fixes_next_speaker_on_disconnect(self):
        room = self._make_room(
            "a",
            ["a", "b", "c"],
            current_speaker="a",
            next_speaker="b",
            turn_state=TurnState.PASSING,
            status=RoomStatus.ACTIVE,
        )
        _reconcile_talking_order(room, {"a", "c"})
        assert room.next_speaker == "c"

    def test_passing_becomes_speaking_when_current_disconnects(self):
        room = self._make_room(
            "a",
            ["a", "b", "c"],
            current_speaker="b",
            next_speaker="c",
            turn_state=TurnState.PASSING,
            status=RoomStatus.ACTIVE,
        )
        _reconcile_talking_order(room, {"a", "c"})
        assert room.current_speaker == "a"
        assert room.turn_state == TurnState.SPEAKING


# ---------------------------------------------------------------------------
# Full apply_event integration tests
# ---------------------------------------------------------------------------


def _setup_room(keeper, attendees):
    """
    Create a Session + Room with the given keeper and attendees.
    Returns (room, session_slug).
    All attendees should include the keeper.
    """
    session = SessionFactory(space__author=keeper)
    for u in attendees:
        session.attendees.add(u)
    room = Room.objects.get_or_create_for_session(session)
    return room, session.slug


@pytest.mark.django_db
class TestStartRoom:
    def test_keeper_starts_room(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        assert state.status == RoomStatus.ACTIVE
        assert state.turn_state == TurnState.SPEAKING
        assert state.current_speaker == keeper.slug
        assert state.next_speaker == user1.slug
        assert state.version == 1

    def test_non_keeper_cannot_start(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, StartRoomEvent(), 0, {keeper.slug, user1.slug})
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_cannot_start_already_active_room(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])
        connected = {keeper.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, StartRoomEvent(), 1, connected)
        assert exc_info.value.code == ErrorCode.ROOM_NOT_WAITING

    def test_start_with_single_participant(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])
        connected = {keeper.slug}

        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        assert state.current_speaker == keeper.slug
        assert state.next_speaker == keeper.slug


@pytest.mark.django_db
class TestPassStick:
    def test_speaker_passes_stick(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        state = apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)

        assert state.turn_state == TurnState.PASSING

    def test_keeper_can_pass_even_if_not_speaker(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        # Start, pass, accept (user1 is now speaking)
        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)

        # Keeper passes even though user1 is speaking
        state = apply_event(slug, keeper.slug, PassStickEvent(), 3, connected)
        assert state.turn_state == TurnState.PASSING

    def test_non_speaker_non_keeper_cannot_pass(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, PassStickEvent(), 1, connected)
        assert exc_info.value.code == ErrorCode.NOT_CURRENT_SPEAKER

    def test_cannot_pass_in_inactive_room(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, PassStickEvent(), 0, {keeper.slug})
        assert exc_info.value.code == ErrorCode.ROOM_NOT_ACTIVE


@pytest.mark.django_db
class TestAcceptStick:
    def test_next_speaker_accepts(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        state = apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)

        assert state.current_speaker == user1.slug
        assert state.next_speaker == keeper.slug
        assert state.turn_state == TurnState.SPEAKING

    def test_wrong_person_cannot_accept(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user2.slug, AcceptStickEvent(), 2, connected)
        assert exc_info.value.code == ErrorCode.NOT_NEXT_SPEAKER

    def test_cannot_accept_when_not_passing(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, AcceptStickEvent(), 1, connected)
        assert exc_info.value.code == ErrorCode.INVALID_TRANSITION


@pytest.mark.django_db
class TestSkipParticipant:
    def test_keeper_skips_next_speaker(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)

        state = apply_event(slug, keeper.slug, SkipParticipantEvent(), 2, connected)

        # user1 was next, got skipped, so user2 should be next
        assert state.next_speaker == user2.slug
        assert state.turn_state == TurnState.PASSING

    def test_non_keeper_cannot_skip(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, SkipParticipantEvent(), 2, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_cannot_skip_when_not_passing(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, SkipParticipantEvent(), 1, connected)
        assert exc_info.value.code == ErrorCode.INVALID_TRANSITION


@pytest.mark.django_db
class TestReorder:
    def test_keeper_reorders(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        # Start so reconciliation sets the order
        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        room = Room.objects.for_session(slug).first()
        current_order = list(room.talking_order)

        # Reverse the order
        new_order = list(reversed(current_order))
        state = apply_event(slug, keeper.slug, ReorderEvent(talking_order=new_order), 1, connected)

        assert state.talking_order == new_order

    def test_non_keeper_cannot_reorder(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        room = Room.objects.for_session(slug).first()
        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, ReorderEvent(talking_order=list(room.talking_order)), 1, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_reorder_must_have_same_participants(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, ReorderEvent(talking_order=["someone_else"]), 1, connected)
        assert exc_info.value.code == ErrorCode.INVALID_PARTICIPANT_ORDER


@pytest.mark.django_db
class TestEndRoom:
    def test_keeper_ends_room(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        state = apply_event(slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), 1, connected)

        assert state.status == RoomStatus.ENDED
        assert state.turn_state == TurnState.IDLE
        assert state.current_speaker is None
        assert state.next_speaker is None

    def test_non_keeper_cannot_end(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), 1, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_cannot_end_inactive_room(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), 0, {keeper.slug})
        assert exc_info.value.code == ErrorCode.ROOM_NOT_ACTIVE


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOptimisticConcurrency:
    def test_stale_version_rejected(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])
        connected = {keeper.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, PassStickEvent(), 0, connected)  # stale
        assert exc_info.value.code == ErrorCode.STALE_VERSION

    def test_version_increments_each_event(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        s1 = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        assert s1.version == 1

        s2 = apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        assert s2.version == 2

        s3 = apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)
        assert s3.version == 3


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAuthorization:
    def test_non_attendee_rejected(self):
        keeper = UserFactory()
        outsider = UserFactory()
        _, slug = _setup_room(keeper, [keeper])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, outsider.slug, StartRoomEvent(), 0, {keeper.slug})
        assert exc_info.value.code == ErrorCode.NOT_IN_ROOM

    def test_room_not_found(self):
        keeper = UserFactory()
        with pytest.raises(TransitionError) as exc_info:
            apply_event("nonexistent-slug", keeper.slug, StartRoomEvent(), 0, set())
        assert exc_info.value.code == ErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# Full turn cycle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFullTurnCycle:
    def test_complete_cycle_three_participants(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        # Start
        s = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        assert s.current_speaker == keeper.slug
        v = s.version

        # Keeper passes
        s = apply_event(slug, keeper.slug, PassStickEvent(), v, connected)
        assert s.turn_state == TurnState.PASSING
        v = s.version

        # Next speaker accepts
        next_slug = s.next_speaker
        assert next_slug
        s = apply_event(slug, next_slug, AcceptStickEvent(), v, connected)
        assert s.current_speaker == next_slug
        assert s.turn_state == TurnState.SPEAKING
        v = s.version

        # That speaker passes
        s = apply_event(slug, next_slug, PassStickEvent(), v, connected)
        v = s.version

        # Next accepts
        next_slug2 = s.next_speaker
        assert next_slug2
        s = apply_event(slug, next_slug2, AcceptStickEvent(), v, connected)
        assert s.current_speaker == next_slug2
        v = s.version

        # End
        s = apply_event(slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), v, connected)
        assert s.status == RoomStatus.ENDED


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEventLog:
    def test_events_are_logged(self):
        from totem.rooms.models import RoomEventLog

        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])
        connected = {keeper.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        room = Room.objects.for_session(slug).first()
        logs = RoomEventLog.objects.filter(room=room)
        assert logs.count() == 1
        log = logs.first()
        assert log
        assert log.event_type == "start_room"
        assert log.actor == keeper.slug
        assert log.version == 1
