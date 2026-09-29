"""
Room state machine.

Pure function of (DB state + event + connected participants) → new state.
No LiveKit calls, no HTTP concerns. Side effects are limited to the database.
"""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from totem.users.models import User

from .models import Room, RoomEventLog
from .schemas import (
    AcceptStickEvent,
    BanParticipantEvent,
    EmptyRoomEvent,
    EndReason,
    EndRoomEvent,
    ErrorCode,
    ForcePassStickEvent,
    ParticipantJoinedEvent,
    PassStickEvent,
    ReorderEvent,
    RoomEvent,
    RoomState,
    RoomStatus,
    SetPromptEvent,
    StartRoomEvent,
    TransitionError,
    TurnState,
    UnbanParticipantEvent,
)


def apply_event(
    session_slug: str,
    actor: str,  # user slug
    event: RoomEvent | EmptyRoomEvent | ParticipantJoinedEvent,
    last_seen_version: int | None,
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

        if isinstance(event, EmptyRoomEvent):
            _require_keeper(room, actor)

        if last_seen_version is not None and room.state_version != last_seen_version:
            raise TransitionError(
                code=ErrorCode.STALE_VERSION,
                message="State has changed since your last read. Re-fetch state and try again.",
                detail=f"expected {last_seen_version}, current {room.state_version}",
            )

        state_before = room.to_state()
        arrivals_before = room.participant_arrivals
        waiting_order_manually_set_before = room.waiting_order_manually_set

        # Reconcile talking order with who's actually connected.
        _reconcile_talking_order(room, connected)

        match event:
            case EmptyRoomEvent():
                # reconciliation already happened above
                pass
            case ParticipantJoinedEvent():
                if room.status == RoomStatus.ACTIVE and actor not in room.banned_participants:
                    first_arrival = actor not in room.participant_arrivals
                    if first_arrival:
                        room.participant_arrivals = {
                            **room.participant_arrivals,
                            actor: timezone.now().isoformat(),
                        }
                    if first_arrival and actor not in {room.current_speaker, room.next_speaker}:
                        room.talking_order = [slug for slug in room.talking_order if slug != actor] + [actor]
                        if room.current_speaker and connected:
                            next_speaker = _next_in_order(room.talking_order, room.current_speaker, connected)
                            if next_speaker is not None:
                                room.next_speaker = next_speaker
            case StartRoomEvent(prompt=prompt):
                _handle_start(room, actor, connected, prompt)
            case PassStickEvent(prompt=prompt):
                _handle_pass(room, actor, connected, prompt)
            case AcceptStickEvent():
                _handle_accept(room, actor, connected)
            case ForcePassStickEvent():
                _handle_force_pass(room, actor, connected)
            case ReorderEvent(talking_order=new_order):
                _handle_reorder(room, actor, new_order, connected)
            case SetPromptEvent(prompt=prompt):
                _handle_set_prompt(room, actor, prompt)
            case EndRoomEvent(reason=reason):
                _handle_end(room, actor, reason)
            case BanParticipantEvent(participant_slug=slug):
                _handle_ban(room, actor, slug, connected)
            case UnbanParticipantEvent(participant_slug=slug):
                _handle_unban(room, actor, slug)
            case _:
                raise AssertionError(f"Unhandled event type: {type(event).__name__}")

        state = room.to_state()
        if state == state_before:
            metadata_fields = []
            if room.participant_arrivals != arrivals_before:
                metadata_fields.append("participant_arrivals")
            if room.waiting_order_manually_set != waiting_order_manually_set_before:
                metadata_fields.append("waiting_order_manually_set")
            if metadata_fields:
                room.save(update_fields=[*metadata_fields, "date_modified"])
            return state

        room.state_version += 1
        room.save(
            update_fields=[
                "status",
                "turn_state",
                "current_speaker",
                "next_speaker",
                "talking_order",
                "participant_arrivals",
                "waiting_order_manually_set",
                "banned_participants",
                "round_number",
                "round_message",
                "state_version",
                "end_reason",
                "date_modified",
            ]
        )

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


def _normalize_prompt(prompt: str | None) -> str | None:
    return (prompt or "").strip() or None


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


def _parse_arrival_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _sort_waiting_room_order(room: Room, connected: set[str]) -> None:
    """Order waiting participants by prior attendance, then arrival time."""
    if room.waiting_order_manually_set:
        return

    arrivals = room.participant_arrivals
    slugs = [slug for slug in room.talking_order if slug != room.keeper]
    attendance_counts = dict(
        User.objects.filter(slug__in=slugs)
        .annotate(
            count=Count(
                "sessions_joined",
                filter=Q(sessions_joined__start__lt=room.session.start, sessions_joined__cancelled=False),
            )
        )
        .values_list("slug", "count")
    )
    positions = {slug: index for index, slug in enumerate(slugs)}
    slugs.sort(
        key=lambda slug: (
            -attendance_counts.get(slug, 0),
            slug not in arrivals,
            _parse_arrival_time(arrivals[slug]) if slug in arrivals else None,
            positions[slug],
        )
    )
    room.talking_order = ([room.keeper] if room.keeper in room.talking_order else []) + slugs


def _reconcile_talking_order(room: Room, connected: set[str]) -> None:
    """
    Reconcile talking_order with connected participants.
    - Keeps disconnected participants in the order (they may reconnect)
    - Appends newly connected participants
    - Keeps the keeper first
    - Starts a pass to the next connected participant when the current
      speaker disconnects
    - Repairs missing speaker assignments
    """
    if room.status == RoomStatus.WAITING_ROOM:
        arrivals = dict(room.participant_arrivals)
        now = timezone.now().isoformat()
        for slug in connected:
            arrivals.setdefault(slug, now)
        room.participant_arrivals = arrivals

    reconciled: list[str] = []

    # Keeper always first
    if room.keeper in set(room.talking_order) | connected:
        reconciled.append(room.keeper)

    # Preserve full existing order (connected and disconnected)
    for slug in room.talking_order:
        if slug not in reconciled:
            reconciled.append(slug)

    # Append newly connected members in arrival order while waiting; otherwise
    # use slug order for deterministic reconciliation.
    newly_connected = [slug for slug in connected if slug not in reconciled]
    if room.status == RoomStatus.WAITING_ROOM:
        newly_connected.sort(key=lambda slug: (_parse_arrival_time(room.participant_arrivals[slug]), slug))
    else:
        newly_connected.sort()
    reconciled.extend(newly_connected)

    room.talking_order = reconciled
    if room.status == RoomStatus.WAITING_ROOM:
        _sort_waiting_room_order(room, connected)

    connected_order = [s for s in room.talking_order if s in connected]

    # An active room must retain its speaker assignments while nobody is
    # connected. Clearing them would leave no reference point from which a
    # later event could recover the turn.
    if room.status != RoomStatus.ACTIVE or not connected_order:
        return

    # A missing assignment has no position from which to continue the order,
    # so recover from the first connected participant.
    if room.current_speaker is None:
        room.current_speaker = connected_order[0]
        room.turn_state = TurnState.SPEAKING

    # A disconnected current speaker remains the source of the handoff until
    # the next speaker accepts.
    elif room.current_speaker not in connected:
        if room.next_speaker not in connected:
            room.next_speaker = (
                _next_in_order(room.talking_order, room.current_speaker, connected) or connected_order[0]
            )
        room.turn_state = TurnState.PASSING
        return

    # Fix next_speaker if missing or absent from connected.
    if room.next_speaker not in connected:
        if room.current_speaker:
            room.next_speaker = _next_in_order(room.talking_order, room.current_speaker, connected)
        else:
            room.next_speaker = connected_order[0]


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _handle_start(room: Room, actor: str, connected: set[str], prompt: str | None) -> None:
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
    room.round_message = _normalize_prompt(prompt)


def _handle_pass(room: Room, actor: str, connected: set[str], prompt: str | None) -> None:
    _require_active(room)
    _require_keeper_in_room(room)

    prompt = _normalize_prompt(prompt)

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

    keeper_passes_from_turn = (
        actor == room.keeper and room.current_speaker == room.keeper and room.turn_state == TurnState.SPEAKING
    )

    if prompt is not None and not keeper_passes_from_turn:
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
        if keeper_passes_from_turn and prompt is not None:
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

    if actor == room.keeper and room.current_speaker != room.keeper:
        # The stick returned to the keeper from another participant, so a
        # full lap completed and a new round begins. A solo keeper passing
        # to themselves is not a lap.
        room.round_number += 1
        room.round_message = None

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


def _handle_set_prompt(room: Room, actor: str, prompt: str) -> None:
    _require_keeper(room, actor)
    _require_active(room)

    room.round_message = _normalize_prompt(prompt)


def _handle_reorder(room: Room, actor: str, new_order: list[str], connected: set[str]) -> None:
    _require_keeper(room, actor)

    new_order = list(dict.fromkeys(new_order))
    if not new_order:
        raise TransitionError(
            code=ErrorCode.INVALID_PARTICIPANT_ORDER,
            message="New order cannot be empty",
        )
    new_set = set(new_order)

    # Every slug in the new order must be in the current talking order.
    # The client may not know about newly-connected participants (added by
    # _reconcile_talking_order), so we allow the new_order to be a subset
    # and append the remaining slugs at the end.
    unknown = new_set - set(room.talking_order)
    if unknown:
        raise TransitionError(
            code=ErrorCode.INVALID_PARTICIPANT_ORDER,
            message="New order contains unknown participants",
            detail=f"Unknown slugs: {', '.join(sorted(unknown))}",
        )

    remaining = [s for s in room.talking_order if s not in new_set]
    room.talking_order = [*new_order, *remaining]
    if room.status == RoomStatus.WAITING_ROOM:
        room.waiting_order_manually_set = True

    # Re-establish the keeper-first invariant via the canonical helper.
    _reconcile_talking_order(room, connected)

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

    # A ban is an explicit removal, not a transient disconnect. Remove the
    # banned speaker assignment so reconciliation recovers from a connected
    # participant instead of retaining them as the source of a handoff.
    if room.current_speaker == participant_slug:
        room.current_speaker = None
        room.turn_state = TurnState.SPEAKING

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
