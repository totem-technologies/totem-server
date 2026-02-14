"""
Room state machine.

Pure function of (DB state + event + connected participants) → new state.
No LiveKit calls, no HTTP concerns. Side effects are limited to the database.
"""

from __future__ import annotations

from django.db import transaction

from .models import Room, RoomEventLog
from .schemas import (
    AcceptStickEvent,
    EndReason,
    EndRoomEvent,
    ErrorCode,
    PassStickEvent,
    ReorderEvent,
    RoomEvent,
    RoomState,
    RoomStatus,
    SkipParticipantEvent,
    StartRoomEvent,
    TransitionError,
    TurnState,
)


def apply_event(
    session_slug: str,
    actor: str,  # user slug
    event: RoomEvent,
    last_seen_version: int,
    connected: set[str],  # user slugs currently in the LiveKit room
) -> RoomState:
    """
    The state machine entry point. Acquires a row lock on the room,
    validates the transition, applies it, and appends to the event log.

    Returns the new RoomState on success.
    Raises TransitionError on any invalid transition.
    """
    with transaction.atomic():
        room = Room.objects.for_session(session_slug).select_for_update().first()  # type: ignore

        if not room:
            raise TransitionError(
                code=ErrorCode.NOT_FOUND,
                message="Room not found",
            )

        _require_attendee(room, actor)

        if room.state_version != last_seen_version:
            raise TransitionError(
                code=ErrorCode.STALE_VERSION,
                message="State has changed since your last read",
                detail=f"expected {last_seen_version}, current {room.state_version}",
            )

        # Reconcile talking order with who's actually connected
        _reconcile_talking_order(room, connected)

        match event:
            case StartRoomEvent():
                _handle_start(room, actor, connected)
            case PassStickEvent():
                _handle_pass(room, actor)
            case AcceptStickEvent():
                _handle_accept(room, actor, connected)
            case SkipParticipantEvent():
                _handle_skip(room, actor, connected)
            case ReorderEvent(talking_order=new_order):
                _handle_reorder(room, actor, new_order)
            case EndRoomEvent(reason=reason):
                _handle_end(room, actor, reason)
            case _:
                raise AssertionError(f"Unhandled event type: {type(event).__name__}")

        room.state_version += 1
        room.save()

        state = room.to_state()

        RoomEventLog.objects.create(
            room=room,
            version=room.state_version,
            event_type=event.type,
            actor=actor,
            snapshot=state.dict(),
        )

    return state


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def _require_keeper(room: Room, actor: str) -> None:
    if actor != room.keeper:
        raise TransitionError(
            code=ErrorCode.NOT_KEEPER,
            message="Only the keeper can perform this action",
        )


def _require_active(room: Room) -> None:
    if room.status != RoomStatus.ACTIVE:
        raise TransitionError(
            code=ErrorCode.ROOM_NOT_ACTIVE,
            message="Room is not active",
        )


def _require_attendee(room: Room, actor: str) -> None:
    if not room.session.attendees.filter(slug=actor).exists():
        raise TransitionError(
            code=ErrorCode.NOT_IN_ROOM,
            message="You are not an attendee of this session",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _next_in_order(
    talking_order: list[str],
    after: str,
    connected: set[str],
) -> str | None:
    """
    Walk the talking order starting after `after`, wrapping around.
    Skips anyone not in `connected`. Returns `after` itself if they're
    the only connected participant. Returns None if nobody is connected.
    """
    if after not in talking_order:
        return None

    start = talking_order.index(after) + 1
    rotated = talking_order[start:] + talking_order[:start]

    for slug in rotated:
        if slug in connected:
            return slug

    # `after` wasn't in rotated (it was excluded by the split),
    # but if they're connected, they're the only one.
    if after in connected:
        return after

    return None


def _reconcile_talking_order(room: Room, connected: set[str]) -> None:
    """
    Sync talking_order with connected participants.
    - Removes disconnected participants
    - Appends newly connected participants
    - Keeps the keeper first
    - Fixes current_speaker/next_speaker if they disconnected
    """
    seen: set[str] = set()
    reconciled: list[str] = []

    # Keeper first if connected
    if room.keeper in connected:
        reconciled.append(room.keeper)
        seen.add(room.keeper)

    # Preserve existing order for members still connected
    for slug in room.talking_order:
        if slug in connected and slug not in seen:
            reconciled.append(slug)
            seen.add(slug)

    # Append any newly connected members
    for slug in connected:
        if slug not in seen:
            reconciled.append(slug)
            seen.add(slug)

    room.talking_order = reconciled

    # Fix current_speaker if they disconnected
    if room.current_speaker and room.current_speaker not in connected:
        room.current_speaker = reconciled[0] if reconciled else None
        if room.turn_state == TurnState.PASSING:
            room.turn_state = TurnState.SPEAKING

    # Fix next_speaker if they disconnected
    if room.next_speaker and room.next_speaker not in connected:
        if room.current_speaker:
            room.next_speaker = _next_in_order(reconciled, room.current_speaker, connected)
        else:
            room.next_speaker = reconciled[0] if reconciled else None


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _handle_start(room: Room, actor: str, connected: set[str]) -> None:
    _require_keeper(room, actor)

    if room.status != RoomStatus.WAITING_ROOM:
        raise TransitionError(
            code=ErrorCode.ROOM_NOT_WAITING,
            message="Room can only be started from the waiting room",
        )

    next_slug = _next_in_order(room.talking_order, room.keeper, connected)

    room.status = RoomStatus.ACTIVE
    room.turn_state = TurnState.SPEAKING
    room.current_speaker = room.keeper
    room.next_speaker = next_slug or room.keeper


def _handle_pass(room: Room, actor: str) -> None:
    _require_active(room)

    if actor != room.current_speaker and actor != room.keeper:
        raise TransitionError(
            code=ErrorCode.NOT_CURRENT_SPEAKER,
            message="Only the current speaker or keeper can pass the stick",
        )

    room.turn_state = TurnState.PASSING


def _handle_accept(room: Room, actor: str, connected: set[str]) -> None:
    _require_active(room)

    if room.turn_state != TurnState.PASSING:
        raise TransitionError(
            code=ErrorCode.INVALID_TRANSITION,
            message="No stick to accept right now",
        )

    if actor != room.next_speaker:
        raise TransitionError(
            code=ErrorCode.NOT_NEXT_SPEAKER,
            message="You are not the next speaker",
        )

    next_slug = _next_in_order(room.talking_order, actor, connected)

    room.current_speaker = actor
    room.next_speaker = next_slug or actor
    room.turn_state = TurnState.SPEAKING


def _handle_skip(room: Room, actor: str, connected: set[str]) -> None:
    _require_active(room)
    _require_keeper(room, actor)

    if room.turn_state != TurnState.PASSING:
        raise TransitionError(
            code=ErrorCode.INVALID_TRANSITION,
            message="No one to skip right now",
        )

    skipped = room.next_speaker

    # Find next person after the skipped one, excluding them.
    candidates = connected - {skipped}
    next_slug = _next_in_order(room.talking_order, skipped, candidates)

    if next_slug is None:
        raise TransitionError(
            code=ErrorCode.INVALID_TRANSITION,
            message="No connected participants to pass the stick to",
        )

    room.next_speaker = next_slug


def _handle_reorder(room: Room, actor: str, new_order: list[str]) -> None:
    _require_keeper(room, actor)

    if set(new_order) != set(room.talking_order):
        raise TransitionError(
            code=ErrorCode.INVALID_PARTICIPANT_ORDER,
            message="New order must contain exactly the same participants",
        )

    room.talking_order = new_order


def _handle_end(room: Room, actor: str, reason: EndReason) -> None:
    _require_keeper(room, actor)
    _require_active(room)

    room.status = RoomStatus.ENDED
    room.turn_state = TurnState.IDLE
    room.current_speaker = None
    room.next_speaker = None
