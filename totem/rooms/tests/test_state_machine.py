import pytest

from totem.rooms.models import Room, RoomEventLog
from totem.rooms.schemas import (
    AcceptStickEvent,
    BanParticipantEvent,
    EmptyRoomEvent,
    EndReason,
    EndRoomEvent,
    ErrorCode,
    ForcePassStickEvent,
    PassStickEvent,
    ReorderEvent,
    RoomStatus,
    SetPromptEvent,
    StartRoomEvent,
    TransitionError,
    TurnState,
    UnbanParticipantEvent,
)
from totem.rooms.state_machine import (
    _next_in_order,
    _reconcile_talking_order,
    _require_keeper_in_room,
    apply_event,
)
from totem.spaces.tests.factories import SessionFactory
from totem.users.models import User
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

    def test_empty_connected_preserves_active_speakers(self):
        room = self._make_room(
            "a",
            ["a", "b", "c"],
            current_speaker="b",
            next_speaker="c",
            turn_state=TurnState.PASSING,
            status=RoomStatus.ACTIVE,
        )

        _reconcile_talking_order(room, set())

        assert room.current_speaker == "b"
        assert room.next_speaker == "c"
        assert room.turn_state == TurnState.PASSING

    def test_repairs_missing_active_speakers_when_participants_reconnect(self):
        room = self._make_room(
            "a",
            ["a", "b", "c"],
            current_speaker=None,
            next_speaker=None,
            turn_state=TurnState.PASSING,
            status=RoomStatus.ACTIVE,
        )

        _reconcile_talking_order(room, {"a", "c"})

        assert room.current_speaker == "a"
        assert room.next_speaker == "c"
        assert room.turn_state == TurnState.SPEAKING

    def test_current_speaker_disconnect_starts_pass_to_next_in_order(self):
        room = self._make_room(
            "a",
            ["a", "b", "c"],
            current_speaker="b",
            turn_state=TurnState.SPEAKING,
            status=RoomStatus.ACTIVE,
        )
        _reconcile_talking_order(room, {"a", "c"})
        assert room.current_speaker == "b"
        assert room.next_speaker == "c"
        assert room.turn_state == TurnState.PASSING

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

    def test_passing_is_preserved_when_current_disconnects_but_next_is_connected(self):
        room = self._make_room(
            "a",
            ["a", "b", "c"],
            current_speaker="b",
            next_speaker="c",
            turn_state=TurnState.PASSING,
            status=RoomStatus.ACTIVE,
        )
        _reconcile_talking_order(room, {"a", "c"})
        assert room.current_speaker == "b"
        assert room.next_speaker == "c"
        assert room.turn_state == TurnState.PASSING

    def test_passing_moves_to_next_connected_when_current_and_next_disconnect(self):
        room = self._make_room(
            "a",
            ["a", "b", "c"],
            current_speaker="b",
            next_speaker="c",
            turn_state=TurnState.PASSING,
            status=RoomStatus.ACTIVE,
        )
        _reconcile_talking_order(room, {"a"})
        assert room.current_speaker == "b"
        assert room.next_speaker == "a"
        assert room.turn_state == TurnState.PASSING


# ---------------------------------------------------------------------------
# Preconditions: _require_keeper_in_room
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRequireKeeperInRoom:
    def _make_room(self, keeper_slug: str, talking_order: list[str], **kwargs) -> Room:
        session = SessionFactory()
        room = Room(
            session=session,
            keeper=keeper_slug,
            talking_order=talking_order,
            **kwargs,
        )
        room.save()
        return room

    def test_raises_when_keeper_missing_from_talking_order(self):
        room = self._make_room("keeper", ["user-1", "user-2"])

        with pytest.raises(TransitionError) as exc_info:
            _require_keeper_in_room(room)

        assert exc_info.value.code == ErrorCode.KEEPER_NOT_IN_ROOM

    def test_allows_when_keeper_present_in_talking_order(self):
        room = self._make_room("keeper", ["keeper", "user-1"])

        _require_keeper_in_room(room)


# ---------------------------------------------------------------------------
# Full apply_event integration tests
# ---------------------------------------------------------------------------


def _setup_room(keeper: User, attendees: list[User]):
    """
    Create a Session + Room with the given keeper and attendees.
    Returns (room, session_slug).
    All attendees should include the keeper.
    Sets talking_order to match the attendees list order so tests are deterministic.
    """
    session = SessionFactory(space__author=keeper)
    for u in attendees:
        session.attendees.add(u)
    room = Room.objects.get_or_create_for_session(session)
    room.talking_order = [u.slug for u in attendees]
    room.save(update_fields=["talking_order"])
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

    def test_start_with_prompt(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        state = apply_event(slug, keeper.slug, StartRoomEvent(prompt="Opening prompt"), 0, connected)

        assert state.status == RoomStatus.ACTIVE
        assert state.round_number == 1
        assert state.round_message == "Opening prompt"

    def test_start_with_empty_prompt_normalizes_to_none(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        state = apply_event(slug, keeper.slug, StartRoomEvent(prompt="   "), 0, connected)

        assert state.round_message is None


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

    def test_pass_rejected_when_keeper_not_in_room(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, {keeper.slug, user1.slug})

        room = Room.objects.for_session(slug).first()
        assert room
        room.talking_order = [s for s in room.talking_order if s != keeper.slug]
        room.save(update_fields=["talking_order"])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, PassStickEvent(), 1, connected)
        assert exc_info.value.code == ErrorCode.KEEPER_NOT_IN_ROOM

    def test_keeper_pass_with_prompt_updates_round_and_message(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        started = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        assert started.round_number == 1
        assert started.round_message is None

        state = apply_event(slug, keeper.slug, PassStickEvent(prompt="What did you learn this week?"), 1, connected)

        assert state.turn_state == TurnState.PASSING
        assert state.round_number == 1
        assert state.round_message == "What did you learn this week?"

    def test_non_keeper_pass_does_not_increment_round(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(prompt="Round 2 prompt"), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)

        state = apply_event(slug, user1.slug, PassStickEvent(), 3, connected)

        assert state.round_number == 1
        assert state.round_message == "Round 2 prompt"

    def test_non_keeper_cannot_set_prompt_when_passing(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, PassStickEvent(prompt="Prompt from participant"), 3, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_speaker_pass_empty_prompt_treated_as_no_prompt(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)

        # Empty prompt normalizes to None, should not trigger the prompt guard
        state = apply_event(slug, user1.slug, PassStickEvent(prompt=""), 3, connected)
        assert state.turn_state == TurnState.PASSING

    def test_keeper_pass_whitespace_prompt_treated_as_no_prompt(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)

        # Keeper passes during someone else's turn, whitespace normalizes away
        state = apply_event(slug, keeper.slug, PassStickEvent(prompt="   "), 3, connected)
        assert state.turn_state == TurnState.PASSING

    def test_prompt_clears_at_round_boundary(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(prompt="Prompt for round 2"), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)
        apply_event(slug, user1.slug, PassStickEvent(), 3, connected)
        apply_event(slug, user2.slug, AcceptStickEvent(), 4, connected)
        apply_event(slug, user2.slug, PassStickEvent(), 5, connected)

        # The stick returns to the keeper, so the prompt clears at the boundary.
        state = apply_event(slug, keeper.slug, AcceptStickEvent(), 6, connected)

        assert state.round_number == 2
        assert state.round_message is None

    def test_keeper_pass_empty_prompt_leaves_start_prompt_intact(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(prompt="Opening prompt"), 0, connected)

        state = apply_event(slug, keeper.slug, PassStickEvent(prompt=""), 1, connected)

        assert state.round_number == 1
        assert state.round_message == "Opening prompt"

    def test_keeper_pass_empty_prompt_leaves_midround_prompt_intact(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, SetPromptEvent(prompt="Mid-round prompt"), 1, connected)

        state = apply_event(slug, keeper.slug, PassStickEvent(prompt=""), 2, connected)

        assert state.round_number == 1
        assert state.round_message == "Mid-round prompt"

    def test_start_prompt_survives_first_pass(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        started = apply_event(slug, keeper.slug, StartRoomEvent(prompt="Opening prompt"), 0, connected)
        assert started.round_number == 1
        assert started.round_message == "Opening prompt"

        state = apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)

        assert state.round_number == 1
        assert state.round_message == "Opening prompt"

        state = apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)
        state = apply_event(slug, user1.slug, PassStickEvent(), 3, connected)

        assert state.round_number == 1
        assert state.round_message == "Opening prompt"

    def test_start_prompt_replaced_by_first_pass_prompt(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(prompt="Opening prompt"), 0, connected)

        state = apply_event(slug, keeper.slug, PassStickEvent(prompt="New prompt"), 1, connected)

        assert state.round_number == 1
        assert state.round_message == "New prompt"

    def test_start_prompt_visible_to_next_speaker(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(prompt="Opening prompt"), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)

        state = apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)

        assert state.round_message == "Opening prompt"

    def test_round_increments_after_full_cycle(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)
        apply_event(slug, user1.slug, PassStickEvent(), 3, connected)
        apply_event(slug, user2.slug, AcceptStickEvent(), 4, connected)
        apply_event(slug, user2.slug, PassStickEvent(), 5, connected)

        # The stick returns to the keeper. Round 1 completes.
        state = apply_event(slug, keeper.slug, AcceptStickEvent(), 6, connected)

        assert state.round_number == 2

    def test_solo_keeper_does_not_lose_prompt_or_overcount(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])
        connected = {keeper.slug}

        started = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        assert started.round_number == 1

        passed = apply_event(slug, keeper.slug, PassStickEvent(prompt="Solo prompt"), 1, connected)
        assert passed.round_number == 1
        assert passed.round_message == "Solo prompt"

        state = apply_event(slug, keeper.slug, AcceptStickEvent(), 2, connected)

        assert state.round_number == 1
        assert state.round_message == "Solo prompt"

    def test_keeper_does_not_overcount_when_participant_disconnects(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        all_connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, all_connected)

        # user1 disconnects while the keeper holds the stick, so the stick
        # points back at the keeper.
        passed = apply_event(slug, keeper.slug, PassStickEvent(prompt="Prompt"), 1, {keeper.slug})
        assert passed.round_message == "Prompt"

        state = apply_event(slug, keeper.slug, AcceptStickEvent(), 2, {keeper.slug})

        assert state.round_number == 1
        assert state.round_message == "Prompt"


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

    def test_pending_speaker_can_accept_after_current_speaker_disconnects(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        all_connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, all_connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, all_connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, all_connected)
        passed = apply_event(slug, user1.slug, PassStickEvent(), 3, all_connected)

        assert passed.current_speaker == user1.slug
        assert passed.next_speaker == user2.slug
        assert passed.turn_state == TurnState.PASSING

        connected_after_disconnect = {keeper.slug, user2.slug}
        reconciled = apply_event(
            slug,
            keeper.slug,
            EmptyRoomEvent(),
            4,
            connected_after_disconnect,
        )

        assert reconciled.current_speaker == user1.slug
        assert reconciled.next_speaker == user2.slug
        assert reconciled.turn_state == TurnState.PASSING

        accepted = apply_event(
            slug,
            user2.slug,
            AcceptStickEvent(),
            5,
            connected_after_disconnect,
        )

        assert accepted.current_speaker == user2.slug
        assert accepted.turn_state == TurnState.SPEAKING

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

    def test_accept_rejected_when_keeper_not_in_room(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, {keeper.slug, user1.slug})
        apply_event(slug, keeper.slug, PassStickEvent(), 1, {keeper.slug, user1.slug})

        room = Room.objects.for_session(slug).first()
        assert room
        room.talking_order = [s for s in room.talking_order if s != keeper.slug]
        room.save(update_fields=["talking_order"])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, AcceptStickEvent(), 2, {user1.slug})
        assert exc_info.value.code == ErrorCode.KEEPER_NOT_IN_ROOM


@pytest.mark.django_db
class TestKeeperPassWhilePassing:
    def test_keeper_pass_skips_next_speaker(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)

        # Keeper passes again while PASSING — skips next_speaker
        state = apply_event(slug, keeper.slug, PassStickEvent(), 2, connected)
        assert state.next_speaker == user2.slug
        assert state.turn_state == TurnState.PASSING

    def test_non_keeper_cannot_pass_while_passing(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, PassStickEvent(), 2, connected)
        assert exc_info.value.code == ErrorCode.NOT_CURRENT_SPEAKER


@pytest.mark.django_db
class TestSetPrompt:
    def test_keeper_sets_prompt_during_session(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        assert state.round_message is None

        state = apply_event(slug, keeper.slug, SetPromptEvent(prompt="What are you carrying?"), 1, connected)
        assert state.round_message == "What are you carrying?"
        assert state.round_number == 1  # prompt change doesn't increment round

    def test_keeper_replaces_prompt(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(prompt="Original prompt"), 1, connected)
        state = apply_event(slug, keeper.slug, SetPromptEvent(prompt="Revised prompt"), 2, connected)

        assert state.round_message == "Revised prompt"
        assert state.round_number == 1

    def test_non_keeper_cannot_set_prompt(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, SetPromptEvent(prompt="Hijacked!"), 1, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_cannot_set_prompt_in_inactive_room(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, SetPromptEvent(prompt="Too early"), 0, connected)
        assert exc_info.value.code == ErrorCode.ROOM_NOT_ACTIVE

    def test_set_prompt_while_keeper_disconnected(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        disconnected = {user1.slug, user2.slug}
        state = apply_event(slug, keeper.slug, SetPromptEvent(prompt="Remote prompt"), 1, disconnected)
        assert state.round_message == "Remote prompt"

    def test_set_prompt_clears_message(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(prompt="Some prompt"), 1, connected)

        state = apply_event(slug, keeper.slug, SetPromptEvent(prompt=""), 2, connected)
        assert state.round_message is None

        state = apply_event(slug, keeper.slug, SetPromptEvent(prompt="New prompt"), 3, connected)
        assert state.round_message == "New prompt"

        state = apply_event(slug, keeper.slug, SetPromptEvent(prompt="   "), 4, connected)
        assert state.round_message is None

    def test_set_prompt_on_ended_room(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), 1, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, SetPromptEvent(prompt="Too late"), 2, connected)
        assert exc_info.value.code == ErrorCode.ROOM_NOT_ACTIVE


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
        assert room
        current_order = list(room.talking_order)

        # Reverse the order
        new_order = list(reversed(current_order))
        state = apply_event(slug, keeper.slug, ReorderEvent(talking_order=new_order), 1, connected)

        # Keeper is expected at first
        assert state.talking_order[0] == keeper.slug
        expected = [keeper.slug] + [s for s in new_order if s != keeper.slug]
        assert state.talking_order == expected

    def test_non_keeper_cannot_reorder(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        room = Room.objects.for_session(slug).first()
        assert room
        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, ReorderEvent(talking_order=list(room.talking_order)), 1, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_reorder_updates_next_speaker(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        # Start — keeper speaking, next is user1
        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        assert state.current_speaker == keeper.slug
        assert state.next_speaker == user1.slug

        # Reorder so user2 comes right after keeper
        new_order = [keeper.slug, user2.slug, user1.slug]
        state = apply_event(slug, keeper.slug, ReorderEvent(talking_order=new_order), 1, connected)

        assert state.talking_order == new_order
        assert state.next_speaker == user2.slug

    def test_reorder_next_speaker_skips_disconnected(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected_all = {keeper.slug, user1.slug, user2.slug}

        # Start with all connected
        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected_all)

        # user1 disconnects, reorder puts user1 right after keeper
        connected = {keeper.slug, user2.slug}
        new_order = [keeper.slug, user1.slug, user2.slug]
        state = apply_event(slug, keeper.slug, ReorderEvent(talking_order=new_order), 1, connected)

        # next_speaker should skip disconnected user1 and land on user2
        assert state.next_speaker == user2.slug

    def test_reorder_rejects_unknown_participant(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, ReorderEvent(talking_order=["someone_else"]), 1, connected)
        assert exc_info.value.code == ErrorCode.INVALID_PARTICIPANT_ORDER
        assert "unknown participants" in exc_info.value.message.lower()
        assert "someone_else" in (exc_info.value.detail or "")

    def test_reorder_rejects_empty_order(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        version_before = state.version

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, ReorderEvent(talking_order=[]), 1, connected)
        assert exc_info.value.code == ErrorCode.INVALID_PARTICIPANT_ORDER

        room = Room.objects.for_session(slug).first()
        assert room
        assert room.state_version == version_before

    def test_reorder_ignores_duplicate_slugs(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        state = apply_event(
            slug, keeper.slug, ReorderEvent(talking_order=[user1.slug, user1.slug, keeper.slug]), 1, connected
        )
        assert state.talking_order == [keeper.slug, user1.slug]

    def test_reorder_when_new_participant_connected(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()
        slug_setup = _setup_room(keeper, [keeper, user1, user2])
        _, slug = slug_setup
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        room = Room.objects.for_session(slug).first()
        assert room
        current_order = list(room.talking_order)

        room.session.attendees.add(user3)
        new_connected = {keeper.slug, user1.slug, user2.slug, user3.slug}

        # Keeper reorders based on the previously seen talking_order (doesn't know about user3 yet)
        new_order = list(reversed(current_order))
        state = apply_event(slug, keeper.slug, ReorderEvent(talking_order=new_order), 1, new_connected)

        expected_head = [keeper.slug] + [s for s in new_order if s != keeper.slug]
        assert state.talking_order[: len(expected_head)] == expected_head
        assert user3.slug in state.talking_order
        assert state.talking_order.index(user3.slug) >= len(expected_head)


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

    def test_cannot_end_already_ended_room(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])
        connected = {keeper.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), 1, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), 2, connected)
        assert exc_info.value.code == ErrorCode.ROOM_ALREADY_ENDED


@pytest.mark.django_db
class TestForcePassStick:
    def test_keeper_force_passes_from_speaking_skips_current(self):
        """
        SCENARIO: Participant accepted but must be skipped.
        A is speaking. Keeper force passes.
        A is cleared, C receives the stick (TurnState.PASSING).
        """
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        # Start -> Keeper is current_speaker (A), user1 is next
        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        assert state.current_speaker == keeper.slug
        assert state.turn_state == TurnState.SPEAKING

        # Keeper force passes -> skips Keeper (A), goes to user1 (C)
        state = apply_event(slug, keeper.slug, ForcePassStickEvent(), 1, connected)

        assert state.current_speaker == keeper.slug
        assert state.next_speaker == user1.slug
        assert state.turn_state == TurnState.PASSING

    def test_keeper_force_passes_from_passing_skips_pending(self):
        """
        SCENARIO: Participant never accepts the totem.
        A is pending. Keeper force passes.
        A is cleared, C receives the stick (TurnState.PASSING).
        """
        user0 = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper=user0, attendees=[user0, user1, user2])
        connected = {user0.slug, user1.slug, user2.slug}

        # Start and Pass -> Keeper passed, user1 is now pending (next_speaker)
        state = apply_event(slug, user0.slug, StartRoomEvent(), 0, connected)
        state = apply_event(slug, user0.slug, PassStickEvent(), 1, connected)

        assert state.turn_state == TurnState.PASSING
        assert state.next_speaker == user1.slug
        assert state.current_speaker == user0.slug

        # Keeper force passes -> skips user1 (A), prompt goes to user2 (C)
        state = apply_event(slug, user0.slug, ForcePassStickEvent(), 2, connected)

        assert state.current_speaker == user0.slug
        assert state.next_speaker == user2.slug
        assert state.turn_state == TurnState.PASSING

    def test_non_keeper_cannot_force_pass(self):
        user0 = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper=user0, attendees=[user0, user1])
        connected = {user0.slug, user1.slug}

        apply_event(slug, user0.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, ForcePassStickEvent(), 1, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_cannot_force_pass_in_inactive_room(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, ForcePassStickEvent(), 0, {keeper.slug})
        assert exc_info.value.code == ErrorCode.ROOM_NOT_ACTIVE


# ---------------------------------------------------------------------------
# Ban / Unban
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBanParticipant:
    def test_ban_adds_to_banned_list(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        state = apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 1, connected)

        assert user1.slug in state.banned_participants

    def test_ban_removes_from_talking_order(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        state = apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 1, connected)

        assert user1.slug not in state.talking_order

    def test_ban_current_speaker_transfers_stick(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)

        state = apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 3, connected)

        assert state.current_speaker == keeper.slug

    def test_ban_current_speaker_while_passing_resets_turn_state(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, PassStickEvent(), 1, connected)
        apply_event(slug, user1.slug, AcceptStickEvent(), 2, connected)
        apply_event(slug, user1.slug, PassStickEvent(), 3, connected)

        state = apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 4, connected)

        assert state.current_speaker != user1.slug
        assert state.turn_state == TurnState.SPEAKING

    def test_ban_next_speaker_reassigns(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        state = apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        assert state.next_speaker == user1.slug

        state = apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 1, connected)

        assert state.next_speaker == user2.slug

    def test_ban_self_raises_error(self):
        keeper = UserFactory()
        _, slug = _setup_room(keeper, [keeper])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=keeper.slug), 0, {keeper.slug})
        assert exc_info.value.code == ErrorCode.INVALID_TRANSITION

    def test_cannot_ban_keeper(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=keeper.slug), 1, connected)
        assert exc_info.value.code == ErrorCode.INVALID_TRANSITION

    def test_ban_already_banned_raises_error(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 1, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 2, {keeper.slug})
        assert exc_info.value.code == ErrorCode.INVALID_TRANSITION

    def test_non_keeper_cannot_ban(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug, user2.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, BanParticipantEvent(participantSlug=user2.slug), 1, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER


@pytest.mark.django_db
class TestUnbanParticipant:
    def test_unban_removes_from_banned_list(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 1, connected)

        state = apply_event(slug, keeper.slug, UnbanParticipantEvent(participantSlug=user1.slug), 2, {keeper.slug})

        assert user1.slug not in state.banned_participants
        assert user1.slug not in state.talking_order

    def test_unban_not_banned_raises_error(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])

        with pytest.raises(TransitionError) as exc_info:
            apply_event(
                slug, keeper.slug, UnbanParticipantEvent(participantSlug=user1.slug), 0, {keeper.slug, user1.slug}
            )
        assert exc_info.value.code == ErrorCode.INVALID_TRANSITION

    def test_non_keeper_cannot_unban(self):
        keeper = UserFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1, user2])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user2.slug), 1, connected)

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, user1.slug, UnbanParticipantEvent(participantSlug=user2.slug), 2, connected)
        assert exc_info.value.code == ErrorCode.NOT_KEEPER

    def test_cannot_unban_in_ended_room(self):
        keeper = UserFactory()
        user1 = UserFactory()
        _, slug = _setup_room(keeper, [keeper, user1])
        connected = {keeper.slug, user1.slug}

        apply_event(slug, keeper.slug, StartRoomEvent(), 0, connected)
        apply_event(slug, keeper.slug, BanParticipantEvent(participantSlug=user1.slug), 1, connected)
        apply_event(slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), 2, {keeper.slug})

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, UnbanParticipantEvent(participantSlug=user1.slug), 3, {keeper.slug})
        assert exc_info.value.code == ErrorCode.ROOM_ALREADY_ENDED


# ---------------------------------------------------------------------------
# Internal reconciliation event
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmptyRoomEvent:
    def test_changed_reconciliation_is_versioned_and_logged(self):
        keeper = UserFactory()
        participant = UserFactory()
        room, slug = _setup_room(keeper, [keeper])

        state = apply_event(slug, keeper.slug, EmptyRoomEvent(), 0, {keeper.slug, participant.slug})

        assert state.version == 1
        assert state.talking_order == [keeper.slug, participant.slug]
        room.refresh_from_db()
        assert room.state_version == 1
        log = RoomEventLog.objects.get(room=room)
        assert log.version == 1
        assert log.event_type == "empty"
        assert log.actor == keeper.slug
        assert log.snapshot == state.model_dump(mode="json")

    def test_noop_reconciliation_is_still_versioned_and_logged(self):
        keeper = UserFactory()
        room, slug = _setup_room(keeper, [keeper])

        state = apply_event(slug, keeper.slug, EmptyRoomEvent(), 0, {keeper.slug})

        assert state.version == 1
        room.refresh_from_db()
        assert room.state_version == 1
        log = RoomEventLog.objects.get(room=room)
        assert log.version == 1
        assert log.event_type == "empty"
        assert log.snapshot == state.model_dump(mode="json")

    def test_reconciliation_invalidates_previous_client_version(self):
        keeper = UserFactory()
        participant = UserFactory()
        _, slug = _setup_room(keeper, [keeper])

        state = apply_event(slug, keeper.slug, EmptyRoomEvent(), 0, {keeper.slug, participant.slug})
        assert state.version == 1

        with pytest.raises(TransitionError) as exc_info:
            apply_event(slug, keeper.slug, StartRoomEvent(), 0, {keeper.slug, participant.slug})

        assert exc_info.value.code == ErrorCode.STALE_VERSION


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
