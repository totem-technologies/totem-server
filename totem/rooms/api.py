"""
Room API endpoints.

This is the composition root — it wires together the state machine,
LiveKit integration, and HTTP concerns. Kept as thin as possible.
"""

from __future__ import annotations

import logging

from django.http import HttpRequest
from ninja import Router

from totem.spaces.models import Session
from totem.users import analytics
from totem.users.models import User

from .livekit import (
    LiveKitConfigurationError,
    create_access_token,
    get_connected_participants,
    mute_all_participants,
    mute_participant,
    publish_state,
    remove_participant,
)
from .models import Room
from .schemas import (
    AcceptStickEvent,
    EndRoomEvent,
    ErrorCode,
    ErrorResponse,
    EventRequest,
    JoinResponse,
    RoomState,
    StartRoomEvent,
    TransitionError,
)
from .state_machine import apply_event

router = Router(tags=["rooms"])

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

ERROR_RESPONSES = {
    400: ErrorResponse,
    403: ErrorResponse,
    404: ErrorResponse,
    409: ErrorResponse,
    500: ErrorResponse,
}

logger = logging.getLogger(__name__)


@router.post(
    "/{session_slug}/event",
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
    session_slug: str,
    body: EventRequest,
):
    user: User = request.user  # type: ignore
    actor = user.slug
    connected = get_connected_participants(session_slug)

    try:
        state = apply_event(
            session_slug=session_slug,
            actor=actor,
            event=body.event,
            last_seen_version=body.last_seen_version,
            connected=connected,
        )
    except TransitionError as e:
        return ErrorResponse(
            code=e.code,
            message=e.message,
            detail=e.detail,
        ).as_http_response()

    # Side effects outside the DB transaction — best-effort.
    # If these fail, clients will catch up via polling.
    publish_state(session_slug, state)

    match body.event:
        case StartRoomEvent():
            mute_all_participants(session_slug, except_identity=state.current_speaker)
        case AcceptStickEvent():
            mute_all_participants(session_slug, except_identity=actor)
        case EndRoomEvent():
            mute_all_participants(session_slug)

    return 200, state


@router.get(
    "/{session_slug}/state",
    response={200: RoomState, **ERROR_RESPONSES},
    summary="Get current room state",
    description=(
        "Returns the current state snapshot. Used by clients on reconnect "
        "or as a fallback poll when LiveKit data messages may have been missed. "
    ),
)
def get_state(
    request: HttpRequest,
    session_slug: str,
):
    user: User = request.user  # type: ignore
    room = Room.objects.for_session(session_slug).first()  # type: ignore

    if not room:
        return 404, ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="Room not found",
        )

    if not room.session.attendees.filter(slug=user.slug).exists():
        return 403, ErrorResponse(
            code=ErrorCode.NOT_IN_ROOM,
            message="You are not an attendee of this session",
        )

    return 200, room.to_state()


# ---------------------------------------------------------------------------
# Join / LiveKit management
# ---------------------------------------------------------------------------


@router.post(
    "/{session_slug}/join",
    response={200: JoinResponse, **ERROR_RESPONSES},
    summary="Join a session room",
    description="Returns a LiveKit access token. Creates the Room if needed.",
)
def join_room(
    request: HttpRequest,
    session_slug: str,
):
    user: User = request.user  # type: ignore

    session = Session.objects.filter(slug=session_slug).first()
    if not session:
        return 404, ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="Session not found",
        )

    if not session.can_join(user):
        return ErrorResponse(
            code=ErrorCode.NOT_JOINABLE,
            message="Session is not joinable at this time",
        ).as_http_response()

    Room.objects.get_or_create_for_session(session)

    try:
        token = create_access_token(user, session.slug)
    except LiveKitConfigurationError:
        logger.exception("LiveKit not configured")
        return ErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR,
            message="LiveKit service is not properly configured",
        ).as_http_response()

    session.joined.add(user)
    analytics.event_joined(user, session)

    return 200, JoinResponse(token=token)


def _get_room_and_require_keeper(user: User, session_slug: str) -> Room | ErrorResponse:
    """Helper: load the Room and verify the user is the keeper. Returns Room or ErrorResponse tuple."""
    room = Room.objects.for_session(session_slug).first()  # type: ignore
    if not room:
        return ErrorResponse(code=ErrorCode.NOT_FOUND, message="Room not found")

    if room.keeper != user.slug:
        return ErrorResponse(code=ErrorCode.NOT_KEEPER, message="Only the keeper can perform this action")

    return room


@router.post(
    "/{session_slug}/mute/{participant_identity}",
    response={200: None, **ERROR_RESPONSES},
    summary="Mute a participant",
    description="Keeper mutes a specific participant's audio.",
)
def mute(
    request: HttpRequest,
    session_slug: str,
    participant_identity: str,
):
    user: User = request.user  # type: ignore
    result = _get_room_and_require_keeper(user, session_slug)
    if isinstance(result, ErrorResponse):
        return result.as_http_response()

    try:
        mute_participant(session_slug, participant_identity)
    except LiveKitConfigurationError:
        return ErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR, message="LiveKit service is not properly configured"
        ).as_http_response()

    return 200, None


@router.post(
    "/{session_slug}/mute-all",
    response={200: None, **ERROR_RESPONSES},
    summary="Mute all participants",
    description="Keeper mutes everyone except themselves.",
)
def mute_all(
    request: HttpRequest,
    session_slug: str,
):
    user: User = request.user  # type: ignore
    result = _get_room_and_require_keeper(user, session_slug)
    if isinstance(result, ErrorResponse):
        return result.as_http_response()

    try:
        mute_all_participants(session_slug, except_identity=user.slug)
    except LiveKitConfigurationError:
        return ErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR, message="LiveKit service is not properly configured"
        ).as_http_response()

    return 200, None


@router.post(
    "/{session_slug}/remove/{participant_identity}",
    response={200: None, **ERROR_RESPONSES},
    summary="Remove a participant",
    description="Keeper removes a participant from the room.",
)
def remove(
    request: HttpRequest,
    session_slug: str,
    participant_identity: str,
):
    user: User = request.user  # type: ignore
    result = _get_room_and_require_keeper(user, session_slug)
    if isinstance(result, ErrorResponse):
        return result.as_http_response()

    if participant_identity == user.slug:
        return ErrorResponse(
            code=ErrorCode.INVALID_TRANSITION,
            message="Cannot remove yourself from the room",
        ).as_http_response()

    try:
        remove_participant(session_slug, participant_identity)
    except LiveKitConfigurationError:
        return ErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR, message="LiveKit service is not properly configured"
        ).as_http_response()

    return 200, None
