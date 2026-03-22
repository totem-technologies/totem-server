"""
Room state machine.

Pure function of (DB state + event + connected participants) → new state.
No LiveKit calls, no HTTP concerns. Side effects are limited to the database.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import Room, RoomEventLog
from .schemas import (
    AcceptStickEvent,
    BanParticipantEvent,
    EndReason,
    EndRoomEvent,
    ErrorCode,
    ForcePassStickEvent,
    PassStickEvent,
    ReorderEvent,
    RoomEvent,
    RoomState,
    RoomStatus,
    StartRoomEvent,
    TransitionError,
    TurnState,
    UnbanParticipantEvent,
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
                message="State has changed since your last read. Re-fetch state and try again.",
                detail=f"expected {last_seen_version}, current {room.state_version}",
            )

        # Reconcile talking order with who's actually connected
        _reconcile_talking_order(room, connected)

        match event:
            case StartRoomEvent():
                _handle_start(room, actor, connected)
            case PassStickEvent(prompt=prompt):
                _handle_pass(room, actor, connected, prompt)
            case AcceptStickEvent():
                _handle_accept(room, actor, connected)
            case ForcePassStickEvent():
                _handle_force_pass(room, actor, connected)
            case ReorderEvent(talking_order=new_order):
                _handle_reorder(room, actor, new_order, connected)
            case EndRoomEvent(reason=reason):
                _handle_end(room, actor, reason)
            case BanParticipantEvent(participant_slug=slug):
                _handle_ban(room, actor, slug, connected)
            case UnbanParticipantEvent(participant_slug=slug):
                _handle_unban(room, actor, slug)
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


def _require_keeper_in_room(room: Room) -> None:
    """Requires the keeper to be in the room to perform an action"""

    if room.keeper not in room.talking_order:
        raise TransitionError(
            code=ErrorCode.KEEPER_NOT_IN_ROOM,
            message="Keeper must be in the room to perform this action",
        )


def _require_active(room: Room) -> None:
    if room.status != RoomStatus.ACTIVE:
        raise TransitionError(
            code=ErrorCode.ROOM_NOT_ACTIVE,
            message="Room is not active",
        )


def _require_not_ended(room: Room) -> None:
    if room.status == RoomStatus.ENDED:
        raise TransitionError(
            code=ErrorCode.ROOM_ALREADY_ENDED,
            message="Room has already ended",
        )


def _require_attendee(room: Room, actor: str) -> None:
    if actor == room.keeper:
        # keeper is always authorized in their own room
        # This check is required because background tasks acting on behalf
        # of the keeper may not be in the attendees list
        return
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
    Reconcile talking_order with connected participants.
    - Keeps disconnected participants in the order (they may reconnect)
    - Appends newly connected participants
    - Keeps the keeper first
    - Fixes current_speaker/next_speaker to connected participants only
    """
    reconciled: list[str] = []

    # Keeper first
    if room.keeper in set(room.talking_order) | connected:
        reconciled.append(room.keeper)

    # Preserve full existing order (connected and disconnected)
    for slug in room.talking_order:
        if slug not in reconciled:
            reconciled.append(slug)

    # Append any newly connected members
    for slug in connected:
        if slug not in reconciled:
            reconciled.append(slug)

    room.talking_order = reconciled

    connected_order = [s for s in reconciled if s in connected]

    # Fix current_speaker if absent from connected (disconnected or banned)
    if room.current_speaker and room.current_speaker not in connected:
        room.current_speaker = connected_order[0] if connected_order else None
        if room.turn_state == TurnState.PASSING:
            room.turn_state = TurnState.SPEAKING

    # Fix next_speaker if absent from connected (disconnected or banned)
    if room.next_speaker and room.next_speaker not in connected:
        if room.current_speaker:
            room.next_speaker = _next_in_order(reconciled, room.current_speaker, connected)
        else:
            room.next_speaker = connected_order[0] if connected_order else None


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
    room.round_number = 1
    room.round_message = None


def _handle_pass(room: Room, actor: str, connected: set[str], prompt: str | None) -> None:
    _require_active(room)
    _require_keeper_in_room(room)

    if actor != room.current_speaker and actor != room.keeper:
        raise TransitionError(
            code=ErrorCode.NOT_CURRENT_SPEAKER,
            message="Only the current speaker or keeper can pass the stick",
        )

    if prompt is not None and actor != room.keeper:
        raise TransitionError(
            code=ErrorCode.NOT_KEEPER,
            message="Only the keeper can set a round prompt",
        )

    keeper_starts_round = (
        actor == room.keeper
        and room.current_speaker == room.keeper
        and room.turn_state == TurnState.SPEAKING
    )

    if prompt is not None and not keeper_starts_round:
        raise TransitionError(
            code=ErrorCode.INVALID_TRANSITION,
            message="Round prompt can only be set when keeper passes from their own turn",
        )

    if room.turn_state == TurnState.PASSING and actor == room.keeper:
        # Keeper passes again while already passing — skip current next_speaker
        skipped = room.next_speaker
        candidates = connected - {skipped}
        next_slug = _next_in_order(room.talking_order, skipped, candidates)

        if next_slug is None:
            raise TransitionError(
                code=ErrorCode.INVALID_TRANSITION,
                message="No connected participants to pass the stick to",
            )

        room.next_speaker = next_slug
    else:
        if keeper_starts_round:
            room.round_number += 1
            room.round_message = prompt
        room.turn_state = TurnState.PASSING


def _handle_accept(room: Room, actor: str, connected: set[str]) -> None:
    _require_active(room)
    _require_keeper_in_room(room)

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


def _handle_force_pass(room: Room, actor: str, connected: set[str]) -> None:
    _require_keeper(room, actor)
    _require_active(room)

    reference_speaker = room.current_speaker if room.turn_state == TurnState.SPEAKING else room.next_speaker
    pass_to = _next_in_order(talking_order=room.talking_order, after=reference_speaker, connected=connected)

    if not pass_to:
        raise TransitionError(
            code=ErrorCode.INVALID_TRANSITION,
            message="No next speaker to force-pass to",
        )

    room.next_speaker = pass_to
    room.turn_state = TurnState.PASSING


def _handle_reorder(room: Room, actor: str, new_order: list[str], connected: set[str]) -> None:
    _require_keeper(room, actor)

    if set(new_order) != set(room.talking_order):
        raise TransitionError(
            code=ErrorCode.INVALID_PARTICIPANT_ORDER,
            message="New order must contain exactly the same participants",
        )

    room.talking_order = new_order
    if room.current_speaker:
        room.next_speaker = _next_in_order(room.talking_order, room.current_speaker, connected)


def _handle_end(room: Room, actor: str, reason: EndReason) -> None:
    _require_keeper(room, actor)
    _require_not_ended(room)

    room.status = RoomStatus.ENDED
    room.turn_state = TurnState.IDLE
    room.current_speaker = None
    room.next_speaker = None
    room.end_reason = reason

    room.session.ended_at = timezone.now()
    room.session.save(update_fields=["ended_at"])


def _handle_ban(room: Room, actor: str, participant_slug: str, connected: set[str]) -> None:
    _require_keeper(room, actor)
    _require_not_ended(room)

    if participant_slug == actor:
        raise TransitionError(
            code=ErrorCode.INVALID_TRANSITION,
            message="Cannot ban yourself",
        )

    if participant_slug in room.banned_participants:
        raise TransitionError(
            code=ErrorCode.INVALID_TRANSITION,
            message="Participant is already banned",
        )

    room.banned_participants = [*room.banned_participants, participant_slug]
    room.talking_order = [s for s in room.talking_order if s != participant_slug]
    _reconcile_talking_order(room, connected - {participant_slug})


def _handle_unban(room: Room, actor: str, participant_slug: str) -> None:
    _require_keeper(room, actor)
    _require_not_ended(room)

    if participant_slug not in room.banned_participants:
        raise TransitionError(
            code=ErrorCode.INVALID_TRANSITION,
            message="Participant is not banned",
        )

    room.banned_participants = [s for s in room.banned_participants if s != participant_slug]
