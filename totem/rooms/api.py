"""
Session state management API.

One POST endpoint for state transitions (events), one GET for current state.
Designed for OpenAPI type generation so Flutter clients get typed models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from django.http import HttpRequest
from ninja import Field, Router, Schema

router = Router(tags=["sessions"])


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SessionStatus(str, Enum):
    LOBBY = "lobby"
    ACTIVE = "active"
    ENDED = "ended"


class TurnState(str, Enum):
    IDLE = "idle"  # lobby or ended, no active turn
    SPEAKING = "speaking"
    PASSING = "passing"  # waiting for next person to accept


class ErrorCode(str, Enum):
    """
    Machine-readable error codes. Clients switch on these, not on messages.
    Add new codes here as needed — the OpenAPI spec will update automatically.
    """

    # Auth / permission
    NOT_IN_SESSION = "not_in_session"
    NOT_MODERATOR = "not_moderator"
    NOT_CURRENT_SPEAKER = "not_current_speaker"
    NOT_PENDING_RECEIVER = "not_pending_receiver"

    # Invalid state transitions
    INVALID_TRANSITION = "invalid_transition"
    SESSION_NOT_ACTIVE = "session_not_active"
    SESSION_NOT_LOBBY = "session_not_lobby"
    SESSION_ALREADY_ENDED = "session_already_ended"

    # Data validation
    INVALID_PARTICIPANT_ORDER = "invalid_participant_order"

    # Concurrency
    STALE_VERSION = "stale_version"

    # Generic
    NOT_FOUND = "not_found"


class EndReason(str, Enum):
    MODERATOR_ENDED = "moderator_ended"
    MODERATOR_ABSENT = "moderator_absent"
    ROOM_EMPTY = "room_empty"


# ---------------------------------------------------------------------------
# State snapshot (shared by GET response and POST response)
# ---------------------------------------------------------------------------


class SessionState(Schema):
    """
    The canonical state snapshot. This is what gets:
    - returned from both endpoints
    - published to LiveKit room metadata
    - stored as the "current" state in the Session model

    Clients should treat this as the single type they deserialize everywhere.
    """

    session_id: uuid.UUID
    version: int
    session_status: SessionStatus
    turn_state: TurnState
    current_speaker_id: Optional[uuid.UUID] = None
    pending_receiver_id: Optional[uuid.UUID] = None
    turn_deadline_utc: Optional[datetime] = None
    talking_order: list[uuid.UUID]
    moderator_id: uuid.UUID


# ---------------------------------------------------------------------------
# Event schemas (discriminated union on `type`)
# ---------------------------------------------------------------------------


class StartSessionEvent(Schema):
    type: Literal["start_session"] = "start_session"


class PassStickEvent(Schema):
    type: Literal["pass_stick"] = "pass_stick"


class AcceptStickEvent(Schema):
    type: Literal["accept_stick"] = "accept_stick"


class SkipParticipantEvent(Schema):
    """Moderator force-skips the pending receiver."""

    type: Literal["skip_participant"] = "skip_participant"


class ReorderEvent(Schema):
    """Moderator reorders the talking order."""

    type: Literal["reorder"] = "reorder"
    talking_order: list[uuid.UUID]


class EndSessionEvent(Schema):
    type: Literal["end_session"] = "end_session"
    reason: EndReason


# The discriminated union. Django Ninja generates a proper oneOf in OpenAPI.
SessionEvent = Annotated[
    Union[
        StartSessionEvent,
        PassStickEvent,
        AcceptStickEvent,
        SkipParticipantEvent,
        ReorderEvent,
        EndSessionEvent,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Request / Response wrappers
# ---------------------------------------------------------------------------


class EventRequest(Schema):
    """
    POST body. Includes the event and the client's last-seen version
    for optimistic concurrency control.
    """

    event: SessionEvent
    last_seen_version: int


class ErrorResponse(Schema):
    """
    Structured error. Clients switch on `code`, display `message`.
    `detail` is optional extra context for debugging.
    """

    code: ErrorCode
    message: str
    detail: Optional[str] = None


class TransitionError(Exception):
    """
    Raised by the state machine when a transition is invalid.
    Carries a typed error code so the endpoint can map it to a response
    without parsing strings or checking subclasses.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        detail: Optional[str] = None,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


# ---------------------------------------------------------------------------
# Placeholder for the state machine (to be implemented)
# ---------------------------------------------------------------------------


def apply_event(
    session_id: uuid.UUID,
    actor_id: uuid.UUID,
    event: SessionEvent,
    last_seen_version: int,
    connected_participant_ids: set[uuid.UUID],
) -> SessionState:
    """
    The state machine entry point. Runs inside a transaction with
    select_for_update on the session row.

    Args:
        session_id: The session to mutate.
        actor_id: Who is submitting the event.
        event: The event to apply.
        last_seen_version: Client's last-seen version for optimistic concurrency.
        connected_participant_ids: Set of participant IDs currently connected
            to the LiveKit room. Passed in by the caller so the state machine
            never talks to LiveKit directly.

    Returns the new SessionState on success.
    Raises TransitionError on any invalid transition.
    """
    # TODO: implement — will be its own module
    raise NotImplementedError


# ---------------------------------------------------------------------------
# LiveKit integration (kept out of the state machine)
# ---------------------------------------------------------------------------


def get_connected_participant_ids(session_id: uuid.UUID) -> set[uuid.UUID]:
    """
    Calls LiveKit's ListParticipants API to get the set of participant IDs
    currently connected to the room.

    This is the only place in the request path that talks to LiveKit.
    The state machine never calls this — it receives the result as an argument.
    """
    # TODO: implement — call livekit RoomService.ListParticipants,
    # extract participant identities, map to UUIDs
    raise NotImplementedError


def publish_state_to_livekit(session_id: uuid.UUID, state: SessionState) -> None:
    """
    Publishes the state snapshot to LiveKit room metadata.
    Called after a successful transition, outside the DB transaction.
    Fire-and-forget — failures here don't roll back the transition.
    """
    # TODO: implement — call livekit RoomService.UpdateRoomMetadata
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# Error responses declared once, reused across endpoints.
ERROR_RESPONSES = {
    400: ErrorResponse,
    403: ErrorResponse,
    404: ErrorResponse,
    409: ErrorResponse,
}


def http_status_for(code: ErrorCode) -> int:
    """Map error codes to HTTP statuses. Defaults to 400."""
    match code:
        case (
            ErrorCode.NOT_IN_SESSION
            | ErrorCode.NOT_MODERATOR
            | ErrorCode.NOT_CURRENT_SPEAKER
            | ErrorCode.NOT_PENDING_RECEIVER
        ):
            return 403
        case ErrorCode.NOT_FOUND:
            return 404
        case ErrorCode.STALE_VERSION:
            return 409
        case _:
            return 400


@router.post(
    "/{session_id}/event",
    response={200: SessionState, **ERROR_RESPONSES},
    summary="Submit a state transition event",
    description=(
        "All state mutations go through this endpoint. "
        "The server validates the transition, persists it, "
        "and broadcasts the new state to LiveKit."
    ),
)
def post_event(
    request: HttpRequest,
    session_id: uuid.UUID,
    body: EventRequest,
):
    actor_id = request.auth.participant_id  # however you resolve the caller
    connected = get_connected_participant_ids(session_id)

    try:
        state = apply_event(
            session_id=session_id,
            actor_id=actor_id,
            event=body.event,
            last_seen_version=body.last_seen_version,
            connected_participant_ids=connected,
        )
    except TransitionError as e:
        return http_status_for(e.code), ErrorResponse(
            code=e.code,
            message=e.message,
            detail=e.detail,
        )

    # Broadcast is best-effort and outside the DB transaction.
    # If this fails, clients will catch up via polling.
    publish_state_to_livekit(session_id, state)

    return 200, state


@router.get(
    "/{session_id}/state",
    response={200: SessionState, 404: ErrorResponse},
    summary="Get current session state",
    description=(
        "Returns the current state snapshot. Used by clients on reconnect "
        "or as a fallback poll when LiveKit data messages may have been missed. "
        "Cheap to call — just a single row read."
    ),
)
def get_state(
    request: HttpRequest,
    session_id: uuid.UUID,
):
    from .models import Session  # deferred to avoid circular imports

    session = Session.objects.filter(id=session_id).first()

    if not session:
        return 404, ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="Session not found",
        )

    return 200, session.to_state_snapshot()
