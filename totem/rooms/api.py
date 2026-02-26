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
    BanParticipantEvent,
    EndRoomEvent,
    ErrorCode,
    EventRequest,
    ForcePassStickEvent,
    JoinResponse,
    RemoveParticipantPayload,
    RemoveReason,
    RoomErrorResponse,
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
    400: RoomErrorResponse,
    403: RoomErrorResponse,
    404: RoomErrorResponse,
    409: RoomErrorResponse,
    500: RoomErrorResponse,
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
        return RoomErrorResponse(
            code=e.code,
            message=e.message,
            detail=e.detail,
        ).as_http_response()

    # Side effects outside the DB transaction — best-effort.
    # If these fail, clients will catch up via polling.
    publish_state(session_slug, state)

    match body.event:
        case StartRoomEvent() | ForcePassStickEvent():
            mute_all_participants(session_slug, except_identity=state.current_speaker)
        case AcceptStickEvent():
            mute_all_participants(session_slug, except_identity=actor)
        case EndRoomEvent():
            mute_all_participants(session_slug)
        case BanParticipantEvent(participant_slug=slug):
            banned_user = User.objects.filter(slug=slug).first()
            if banned_user is not None:
                analytics.user_banned_from_room(banned_user, session_slug)
            remove_participant(session_slug, slug, reason=RemoveReason.BAN)

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
        return 404, RoomErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="Room not found",
        )

    if not room.session.attendees.filter(slug=user.slug).exists():
        return 403, RoomErrorResponse(
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
        return 404, RoomErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="Session not found",
        )

    if not session.can_join(user):
        return RoomErrorResponse(
            code=ErrorCode.NOT_JOINABLE,
            message="Session is not joinable at this time",
        ).as_http_response()

    room = Room.objects.get_or_create_for_session(session)
    if user.slug in room.banned_participants:
        return RoomErrorResponse(
            code=ErrorCode.BANNED,
            message="You have been banned from this session",
        ).as_http_response()

    try:
        token = create_access_token(user, session.slug)
    except LiveKitConfigurationError:
        logger.exception("LiveKit not configured")
        return RoomErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR,
            message="LiveKit service is not properly configured",
        ).as_http_response()

    is_already_connected = False
    if session.joined.count() > 0:
        try:
            is_already_connected = user.slug in get_connected_participants(session_slug)
        except Exception:
            logger.exception("Failed to determine if user is already connected to LiveKit")

    session.joined.add(user)
    analytics.event_joined(user, session)

    return 200, JoinResponse(token=token, is_already_present=is_already_connected)


def _get_room_and_require_keeper(user: User, session_slug: str) -> Room | RoomErrorResponse:
    """Helper: load the Room and verify the user is the keeper. Returns Room or ErrorResponse tuple."""
    room = Room.objects.for_session(session_slug).first()  # type: ignore
    if not room:
        return RoomErrorResponse(code=ErrorCode.NOT_FOUND, message="Room not found")

    if room.keeper != user.slug:
        return RoomErrorResponse(code=ErrorCode.NOT_KEEPER, message="Only the keeper can perform this action")

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
    if isinstance(result, RoomErrorResponse):
        return result.as_http_response()

    try:
        mute_participant(session_slug, participant_identity)
    except LiveKitConfigurationError:
        return RoomErrorResponse(
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
    if isinstance(result, RoomErrorResponse):
        return result.as_http_response()

    try:
        mute_all_participants(session_slug, except_identity=user.slug)
    except LiveKitConfigurationError:
        return RoomErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR, message="LiveKit service is not properly configured"
        ).as_http_response()

    return 200, None


@router.post(
    "/{session_slug}/remove/{participant_identity}",
    response={200: RemoveParticipantPayload, **ERROR_RESPONSES},
    summary="Remove a participant",
    description="Emits a remove event to a specific participant",
)
def remove(
    request: HttpRequest,
    session_slug: str,
    participant_identity: str,
    reason: RemoveReason = RemoveReason.REMOVE,
):
    user: User = request.user  # type: ignore
    result = _get_room_and_require_keeper(user, session_slug)
    if isinstance(result, RoomErrorResponse):
        return result.as_http_response()

    if participant_identity == user.slug:
        return RoomErrorResponse(
            code=ErrorCode.INVALID_TRANSITION,
            message="Cannot remove yourself from the room",
        ).as_http_response()

    try:
        remove_participant(session_slug, participant_identity, reason=reason)
    except LiveKitConfigurationError:
        return RoomErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR, message="LiveKit service is not properly configured"
        ).as_http_response()

    room: Room = result
    analytics.user_removed_from_room(user, room.session)

    return 200, RemoveParticipantPayload(identity=participant_identity, reason=reason)
