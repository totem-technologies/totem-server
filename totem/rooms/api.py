"""
Room API endpoints.

This is the composition root — it wires together the state machine,
LiveKit integration, and HTTP concerns. Kept as thin as possible.
"""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from .livekit import get_connected_participants, publish_state
from .models import Room
from .schemas import (
    ErrorCode,
    ErrorResponse,
    EventRequest,
    RoomState,
    TransitionError,
)
from .state_machine import apply_event

router = Router(tags=["rooms"])


# ---------------------------------------------------------------------------
# HTTP mapping (only HTTP-aware code in the app)
# ---------------------------------------------------------------------------


def http_status_for(code: ErrorCode) -> int:
    """Map error codes to HTTP statuses. Defaults to 400."""
    match code:
        case ErrorCode.NOT_IN_ROOM | ErrorCode.NOT_KEEPER | ErrorCode.NOT_CURRENT_SPEAKER | ErrorCode.NOT_NEXT_SPEAKER:
            return 403
        case ErrorCode.NOT_FOUND:
            return 404
        case ErrorCode.STALE_VERSION:
            return 409
        case _:
            return 400


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

ERROR_RESPONSES = {
    400: ErrorResponse,
    403: ErrorResponse,
    404: ErrorResponse,
    409: ErrorResponse,
}


@router.post(
    "/{room_id}/event",
    response={200: RoomState, **ERROR_RESPONSES},
    summary="Submit a state transition event",
    description=(
        "All state mutations go through this endpoint. "
        "The server validates the transition, persists it, "
        "and broadcasts the new state to LiveKit."
    ),
)
def post_event(
    request: HttpRequest,
    room_id: int,
    body: EventRequest,
):
    actor = request.auth.slug  # however you resolve the caller's slug
    connected = get_connected_participants(room_id)

    try:
        state = apply_event(
            room_id=room_id,
            actor=actor,
            event=body.event,
            last_seen_version=body.last_seen_version,
            connected=connected,
        )
    except TransitionError as e:
        return http_status_for(e.code), ErrorResponse(
            code=e.code,
            message=e.message,
            detail=e.detail,
        )

    # Broadcast is best-effort and outside the DB transaction.
    # If this fails, clients will catch up via polling.
    publish_state(room_id, state)

    return 200, state


@router.get(
    "/{room_id}/state",
    response={200: RoomState, 404: ErrorResponse},
    summary="Get current room state",
    description=(
        "Returns the current state snapshot. Used by clients on reconnect "
        "or as a fallback poll when LiveKit data messages may have been missed. "
        "Cheap to call — just a single row read."
    ),
)
def get_state(
    request: HttpRequest,
    room_id: int,
):
    room = Room.objects.filter(session_id=room_id).first()

    if not room:
        return 404, ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="Room not found",
        )

    return 200, room.to_state()
