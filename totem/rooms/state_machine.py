"""
Room state machine.

State transitions are derived from DB state, events, and connected participants.
HTTP remains outside this module; prompt CRUD may schedule best-effort LiveKit publication after commit.

Locking: every write to a session's Room, SessionPrompts and SessionRounds
happens while holding the Session row lock (select_for_update). That single
lock serializes the writers, so the child rows are never locked themselves.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from .livekit import publish_state
from .models import Room, RoomEventLog
from .schemas import (
    AcceptStickEvent,
    BanParticipantEvent,
    EmptyRoomEvent,
    EndReason,
    EndRoomEvent,
    ErrorCode,
    ForcePassStickEvent,
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

if TYPE_CHECKING:
    from totem.spaces.models import Session


def apply_event(
    session_slug: str,
    actor: str,  # user slug
    event: RoomEvent | EmptyRoomEvent,
    last_seen_version: int | None,
    connected: set[str],  # user slugs currently in the LiveKit room
) -> RoomState:
    """
    The state machine entry point. Acquires the Session row lock,
    validates the transition, applies it, and appends to the event log.

    Returns the new RoomState on success.
    Raises TransitionError on any invalid transition.
    """
    with transaction.atomic():
        from totem.spaces.models import Session

        session = Session.objects.select_for_update().filter(slug=session_slug).first()
        room = _get_room(session) if session else None
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

        # Reconcile talking order with who's actually connected.
        _reconcile_talking_order(room, connected)

        match event:
            case EmptyRoomEvent():
                # reconciliation already happened above
                pass
            case StartRoomEvent(prompt=prompt):
                _handle_start(room, actor, connected, prompt)
            case PassStickEvent(prompt=prompt, session_prompt_id=session_prompt_id):
                _handle_pass(room, actor, connected, prompt, session_prompt_id)
            case AcceptStickEvent():
                _handle_accept(room, actor, connected)
            case ForcePassStickEvent():
                _handle_force_pass(room, actor, connected)
            case ReorderEvent(talking_order=new_order):
                _handle_reorder(room, actor, new_order, connected)
            case SetPromptEvent(prompt=prompt, session_prompt_id=session_prompt_id):
                _handle_set_prompt(room, actor, prompt, session_prompt_id)
            case EndRoomEvent(reason=reason):
                _handle_end(room, actor, reason)
            case BanParticipantEvent(participant_slug=slug):
                _handle_ban(room, actor, slug, connected)
            case UnbanParticipantEvent(participant_slug=slug):
                _handle_unban(room, actor, slug)
            case _:
                raise AssertionError(f"Unhandled event type: {type(event).__name__}")

        state = persist_room_state_change(room, state_before, event.type, actor)

    return state


def _get_room(session: Session) -> Room | None:
    room = Room.objects.filter(session=session).first()
    if room:
        room.session = session
    return room


@contextmanager
def syncing_session_prompts(session: Session, actor: str) -> Iterator[None]:
    """
    Wrap writes to a session's prepared prompts. The caller must hold the
    Session row lock inside a transaction.

    Afterwards, active rounds pick up edited prompt text (or lose it when the
    prompt was deleted), prompts_revision is bumped if anything changed, and
    the new room state is published after commit.
    """
    from totem.spaces.models import SessionRound, SessionRoundState

    room = _get_room(session)
    state_before = room.to_state() if room else None
    prompts_before = list(session.discussion_prompts.values_list("pk", "prompt", "position"))
    active_rounds = list(
        SessionRound.objects.filter(session=session, state=SessionRoundState.ACTIVE, prepared_prompt__isnull=False)
    )

    yield

    prompts_after = list(session.discussion_prompts.values_list("pk", "prompt", "position"))
    if prompts_after == prompts_before:
        return

    prompt_text = {pk: prompt for pk, prompt, _ in prompts_after}
    changed_rounds = []
    for round in active_rounds:
        text = prompt_text.get(round.prepared_prompt_id, "")
        if round.prompt != text:
            round.prompt = text
            round.date_modified = timezone.now()
            changed_rounds.append(round)
    SessionRound.objects.bulk_update(changed_rounds, ["prompt", "date_modified"])

    _bump_prompts_revision(session)
    if room and state_before:
        persist_room_state_change(room, state_before, "update_session_prompts", actor, publish=True)


def _bump_prompts_revision(session: Session) -> None:
    session.prompts_revision += 1
    session.save(update_fields=["prompts_revision", "date_modified"])


def persist_room_state_change(
    room: Room,
    state_before: RoomState,
    event_type: str,
    actor: str,
    *,
    publish: bool = False,
) -> RoomState:
    """Persist a versioned RoomState transition while the caller holds the Session row lock."""
    state = room.to_state()
    if state == state_before:
        return state

    room.state_version += 1
    room.save()
    state = state.model_copy(update={"version": room.state_version})
    RoomEventLog.objects.create(
        room=room,
        version=room.state_version,
        event_type=event_type,
        actor=actor,
        snapshot=state.dict(),
    )
    if publish:
        transaction.on_commit(partial(publish_state, room.session.slug, state))
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


def _set_round_prompt(room: Room, prompt: str | None, session_prompt_id: int | None = None) -> None:
    from totem.spaces.models import SessionPrompt, SessionRound, SessionRoundState

    prompt = _normalize_prompt(prompt)
    prepared_prompt = None
    if session_prompt_id is not None:
        if prompt is not None:
            raise TransitionError(
                code=ErrorCode.INVALID_TRANSITION,
                message="Choose either a prepared prompt or a custom prompt",
            )
        prepared_prompt = SessionPrompt.objects.filter(session=room.session, pk=session_prompt_id).first()
        if prepared_prompt is None:
            raise TransitionError(
                code=ErrorCode.INVALID_TRANSITION,
                message="Prepared prompt does not belong to this session",
            )

        prompt = prepared_prompt.prompt

    round, created = SessionRound.objects.get_or_create(
        session=room.session,
        number=room.round_number,
        defaults={"prompt": prompt or "", "prepared_prompt": prepared_prompt},
    )
    previous_prepared_prompt_id = None if created else round.prepared_prompt_id
    if not created:
        round.prompt = prompt or ""
        round.prepared_prompt = prepared_prompt
        # A room restarted from the admin reuses round numbers from its earlier run.
        round.state = SessionRoundState.ACTIVE
        round.save(update_fields=["prompt", "prepared_prompt", "state", "date_modified"])
    # Prepared prompts report which rounds consumed them, so changing a
    # round's prepared prompt changes the prompt list clients cache.
    if round.prepared_prompt_id != previous_prepared_prompt_id:
        _bump_prompts_revision(room.session)


def _complete_current_round(room: Room) -> None:
    from totem.spaces.models import SessionRound, SessionRoundState

    SessionRound.objects.filter(
        session=room.session,
        number=room.round_number,
        state=SessionRoundState.ACTIVE,
    ).update(state=SessionRoundState.COMPLETED)


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
    - Starts a pass to the next connected participant when the current
      speaker disconnects
    - Repairs missing speaker assignments
    """
    reconciled: list[str] = []

    # Keeper always first
    if room.keeper in set(room.talking_order) | connected:
        reconciled.append(room.keeper)

    # Preserve full existing order (connected and disconnected)
    for slug in room.talking_order:
        if slug not in reconciled:
            reconciled.append(slug)

    # Append any newly connected members (sorted for deterministic order)
    for slug in sorted(connected):
        if slug not in reconciled:
            reconciled.append(slug)

    room.talking_order = reconciled

    connected_order = [s for s in reconciled if s in connected]

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
            room.next_speaker = _next_in_order(reconciled, room.current_speaker, connected) or connected_order[0]
        room.turn_state = TurnState.PASSING
        return

    # Fix next_speaker if missing or absent from connected.
    if room.next_speaker not in connected:
        if room.current_speaker:
            room.next_speaker = _next_in_order(reconciled, room.current_speaker, connected)
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
    _set_round_prompt(room, prompt)


def _handle_pass(
    room: Room,
    actor: str,
    connected: set[str],
    prompt: str | None,
    session_prompt_id: int | None,
) -> None:
    _require_active(room)
    _require_keeper_in_room(room)

    prompt = _normalize_prompt(prompt)
    sets_prompt = prompt is not None or session_prompt_id is not None

    if actor != room.current_speaker and actor != room.keeper:
        raise TransitionError(
            code=ErrorCode.NOT_CURRENT_SPEAKER,
            message="Only the current speaker or keeper can pass the stick",
        )

    if sets_prompt and actor != room.keeper:
        raise TransitionError(
            code=ErrorCode.NOT_KEEPER,
            message="Only the keeper can set a round prompt",
        )

    keeper_passes_from_turn = (
        actor == room.keeper and room.current_speaker == room.keeper and room.turn_state == TurnState.SPEAKING
    )

    if sets_prompt and not keeper_passes_from_turn:
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
        if sets_prompt:
            _set_round_prompt(room, prompt, session_prompt_id)
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
        _complete_current_round(room)
        room.round_number += 1
        _set_round_prompt(room, None)

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


def _handle_set_prompt(room: Room, actor: str, prompt: str | None, session_prompt_id: int | None) -> None:
    _require_keeper(room, actor)
    _require_active(room)

    _set_round_prompt(room, prompt, session_prompt_id)


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

    # Re-establish the keeper-first invariant via the canonical helper.
    _reconcile_talking_order(room, connected)

    if room.current_speaker:
        room.next_speaker = _next_in_order(room.talking_order, room.current_speaker, connected)


def _handle_end(room: Room, actor: str, reason: EndReason) -> None:
    _require_keeper(room, actor)
    _require_not_ended(room)

    _complete_current_round(room)
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
