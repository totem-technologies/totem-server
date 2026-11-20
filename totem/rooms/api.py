"""
Room API endpoints.

This is the composition root — it wires together the state machine,
LiveKit integration, and HTTP concerns. Kept as thin as possible.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status
from pydantic import ValidationError

from totem.spaces.models import Session, Space
from totem.users import analytics
from totem.users.models import User

from .admission.api import router as admission_router
from .livekit import (
    LiveKitConfigurationError,
    LiveKitPermissionError,
    create_access_token,
    disable_camera_participant,
    get_admission_participants,
    get_connected_participants,
    get_room_participant_sids,
    mute_all_participants,
    mute_participant,
    publish_state,
    remove_participant,
)
from .models import Room
from .schemas import (
    AcceptStickEvent,
    AdmissionJoinRequest,
    BanParticipantEvent,
    EmptyRoomEvent,
    EndRoomEvent,
    ErrorCode,
    EventRequest,
    ForcePassStickEvent,
    JoinResponse,
    RemoveParticipantPayload,
    RemoveReason,
    RoomErrorResponse,
    RoomState,
    RoomStatus,
    StartRoomEvent,
    TransitionError,
    UnbanParticipantEvent,
)
from .state_machine import apply_event, record_join

router = Router(tags=["rooms"])
router.add_router("", admission_router)

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
    participant_sids = None
    if settings.SERVER_ENFORCED_ADMISSION:
        try:
            participant_sids = get_room_participant_sids(session_slug)
            connected = set(participant_sids)
        except LiveKitPermissionError as error:
            if not isinstance(body.event, EndRoomEvent | BanParticipantEvent | UnbanParticipantEvent):
                return _livekit_error(error)
            connected = None
    else:
        connected = get_connected_participants(session_slug)

    identities = None
    if settings.SERVER_ENFORCED_ADMISSION and connected is not None:
        identities = _project_connected(session_slug, connected, participant_sids=participant_sids)

    try:
        state = apply_event(
            session_slug=session_slug,
            actor=actor,
            event=body.event,
            last_seen_version=body.last_seen_version,
            connected=connected,
            **({"participant_sids": participant_sids} if settings.SERVER_ENFORCED_ADMISSION else {}),
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
            mute_all_participants(
                session_slug,
                except_identity=state.current_speaker,
                **({"identities": identities} if settings.SERVER_ENFORCED_ADMISSION else {}),
            )
        case AcceptStickEvent():
            mute_all_participants(
                session_slug,
                except_identity=actor,
                **({"identities": identities} if settings.SERVER_ENFORCED_ADMISSION else {}),
            )
        case EndRoomEvent():
            if settings.SERVER_ENFORCED_ADMISSION:
                mute_all_participants(session_slug, identities=identities or set())
            else:
                mute_all_participants(session_slug)
        case BanParticipantEvent(participant_slug=slug):
            banned_user = User.objects.filter(slug=slug).first()
            if banned_user is not None:
                analytics.user_banned_from_room(banned_user, session_slug)
            try:
                remove_participant(session_slug, slug, reason=RemoveReason.BAN)
            except LiveKitPermissionError as error:
                if error.code not in {"participant_missing", "room_missing"}:
                    return _livekit_error(error)

    return Status(200, state)


@router.get(
    "/{session_slug}/state",
    response={200: RoomState, **ERROR_RESPONSES},
    summary="Get current room state",
    description=(
        "Returns the current state snapshot. Used by clients on reconnect "
        "or as a fallback poll when LiveKit data messages may have been missed. "
    ),
)
def get_state(request: HttpRequest, session_slug: str):
    user: User = request.user  # type: ignore
    room = Room.objects.for_session(session_slug).first()  # type: ignore

    if not room:
        return Status(
            404,
            RoomErrorResponse(
                code=ErrorCode.NOT_FOUND,
                message="Room not found",
            ),
        )

    if not room.session.attendees.filter(slug=user.slug).exists():
        return Status(
            403,
            RoomErrorResponse(
                code=ErrorCode.NOT_IN_ROOM,
                message="You are not an attendee of this session",
            ),
        )

    return Status(200, room.to_state())


@router.post(
    "/{session_slug}/state/reconcile",
    response={200: RoomState, **ERROR_RESPONSES},
    summary="Reconcile room state",
    description=(
        "Keeper-only command that reconciles room state with connected "
        "LiveKit participants and broadcasts the resulting state."
    ),
)
def reconcile_room(request: HttpRequest, session_slug: str):
    connected: set[str] | None
    user: User = request.user  # type: ignore
    result = _get_room_and_require_keeper(user, session_slug)
    if isinstance(result, RoomErrorResponse):
        return result.as_http_response()

    participant_sids = None
    if settings.SERVER_ENFORCED_ADMISSION:
        try:
            participant_sids = get_room_participant_sids(session_slug)
            connected = set(participant_sids)
        except LiveKitPermissionError as error:
            return _livekit_error(error)
    else:
        connected = get_connected_participants(session_slug)
        if not connected:
            return Status(200, result.to_state())

    try:
        state = apply_event(
            session_slug=session_slug,
            actor=user.slug,
            event=EmptyRoomEvent(),
            last_seen_version=None,
            connected=connected,
            **({"participant_sids": participant_sids} if settings.SERVER_ENFORCED_ADMISSION else {}),
        )
    except TransitionError as e:
        return RoomErrorResponse(
            code=e.code,
            message=e.message,
            detail=e.detail,
        ).as_http_response()

    # Side effect outside the DB transaction — best-effort.
    publish_state(session_slug, state)
    return Status(200, state)


# ---------------------------------------------------------------------------
# Join / LiveKit management
# ---------------------------------------------------------------------------


@router.post(
    "/{session_slug}/join",
    response={200: JoinResponse, **ERROR_RESPONSES},
    summary="Join a session room",
    description="Returns a LiveKit access token. Creates the Room if needed.",
    openapi_extra={
        "requestBody": {
            "required": False,
            "content": {"application/json": {"schema": AdmissionJoinRequest.model_json_schema()}},
        },
    },
)
def join_room(
    request: HttpRequest,
    session_slug: str,
):
    user: User = request.user  # type: ignore

    session = Session.objects.select_related("space", "room").filter(slug=session_slug).first()
    if not session:
        return Status(
            404,
            RoomErrorResponse(
                code=ErrorCode.NOT_FOUND,
                message="Session not found",
            ),
        )

    if settings.SERVER_ENFORCED_ADMISSION and session.space.meeting_provider == Space.MeetingProviderChoices.LIVEKIT:
        body = None
        # Legacy no-body/form POSTs remain valid. Only explicit JSON supplies IDs.
        if request.content_type == "application/json" and request.body:
            try:
                body = AdmissionJoinRequest.model_validate_json(request.body)
            except ValidationError:
                return RoomErrorResponse(
                    code=ErrorCode.INVALID_TRANSITION, message="Both admission UUIDs are required"
                ).as_http_response()
        return _join_with_admission(session, user, body)

    if session.space.meeting_provider != Space.MeetingProviderChoices.LIVEKIT or not session.can_join(user):
        return RoomErrorResponse(
            code=ErrorCode.NOT_JOINABLE,
            message="Session is not joinable at this time",
        ).as_http_response()

    room = Room.objects.get_or_create_for_session(session)
    if room.status == RoomStatus.ENDED:
        return RoomErrorResponse(
            code=ErrorCode.ROOM_ALREADY_ENDED,
            message="This session has ended",
        ).as_http_response()

    now = timezone.now()
    need_participants = (now > session.end() and user.slug != room.keeper) or session.joined.count() > 0
    connected: set[str] | None = None
    if need_participants:
        try:
            connected = get_connected_participants(session_slug)
        except Exception:
            logger.exception("Failed to fetch connected participants from LiveKit")

    if now > session.end() and user.slug != room.keeper:
        if connected is not None and len(connected) == 0:
            return RoomErrorResponse(
                code=ErrorCode.NOT_JOINABLE,
                message="This session has ended",
            ).as_http_response()

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

    is_already_connected = bool(connected and user.slug in connected)

    try:
        record_join(session, user)
    except TransitionError as e:
        return RoomErrorResponse(code=e.code, message=e.message, detail=e.detail).as_http_response()

    analytics.event_joined(user, session)

    return Status(200, JoinResponse(token=token, is_already_present=is_already_connected))


def _join_with_admission(session: Session, user: User, body: AdmissionJoinRequest | None):
    from .admission import AdmissionError, prepare_admission_join

    if not user.is_active or not session.attendees.filter(pk=user.pk).exists():
        return RoomErrorResponse(
            code=ErrorCode.NOT_JOINABLE, message="You are not an eligible attendee"
        ).as_http_response()
    try:
        # Always check presence: waiting token requests are not Session.joined.
        connected = get_admission_participants(session.slug)
        room = Room.objects.filter(session=session).first()
        keeper = room.keeper if room else session.space.author.slug
        if timezone.now() > session.end() and user.slug != keeper and not connected:
            return RoomErrorResponse(code=ErrorCode.NOT_JOINABLE, message="This session has ended").as_http_response()
        response = prepare_admission_join(
            session.slug,
            user,
            request_id=body.request_id if body else None,
            attempt_id=body.attempt_id if body else None,
            connected=connected,
        )
    except AdmissionError as error:
        capacity_codes = {
            "admission_full": "ADMISSION_FULL",
            "waiting_full": "WAITING_ROOM_FULL",
            "room_full": "ROOM_FULL",
        }
        if error.code in capacity_codes and hasattr(ErrorCode, capacity_codes[error.code]):
            code = getattr(ErrorCode, capacity_codes[error.code])
            return Status(409, RoomErrorResponse(code=code, message=str(error), detail=error.code))
        code = ErrorCode.ROOM_ALREADY_ENDED if error.code == "ended" else ErrorCode.NOT_JOINABLE
        return RoomErrorResponse(code=code, message=str(error), detail=error.code).as_http_response()
    except TransitionError as error:
        return RoomErrorResponse(code=error.code, message=error.message, detail=error.detail).as_http_response()
    except (LiveKitPermissionError, LiveKitConfigurationError) as error:
        return RoomErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR,
            message="LiveKit admission service is unavailable",
            detail=getattr(error, "code", "unavailable"),
        ).as_http_response()
    response.is_already_present = user.slug in connected

    return Status(200, response)


def _livekit_error(error: Exception):
    return RoomErrorResponse(
        code=ErrorCode.LIVEKIT_ERROR,
        message="LiveKit service is unavailable",
        detail=getattr(error, "code", "unavailable"),
    ).as_http_response()


def _project_connected(
    session_slug: str, connected: set[str], actor: User | None = None, *, participant_sids: dict[str, str] | None
):
    from .room_participants import participant_projection

    with transaction.atomic():
        session = Session.objects.select_for_update().filter(slug=session_slug).first()
        room = Room.objects.filter(session=session).first() if session else None
        if room is None:
            return RoomErrorResponse(code=ErrorCode.NOT_FOUND, message="Room not found") if actor else set()
        if actor and room.keeper != actor.slug:
            return RoomErrorResponse(code=ErrorCode.NOT_KEEPER, message="Only the keeper can perform this action")
        return participant_projection(room, connected, observed_sids=participant_sids).connected


def _get_room_and_require_keeper(user: User, session_slug: str) -> Room | RoomErrorResponse:
    """Helper: load the Room and verify the user is the keeper. Returns Room or ErrorResponse tuple."""
    room = Room.objects.for_session(session_slug).first()  # type: ignore
    if not room:
        return RoomErrorResponse(code=ErrorCode.NOT_FOUND, message="Room not found")

    if room.keeper != user.slug:
        return RoomErrorResponse(code=ErrorCode.NOT_KEEPER, message="Only the keeper can perform this action")

    return room


def _keeper_livekit_action(
    user: User, session_slug: str, action: Callable[[set[str] | None], None], target: str | None = None
):
    """Helper: verify the user is the keeper, then run a LiveKit call with shared error handling."""
    result = _get_room_and_require_keeper(user, session_slug)
    if isinstance(result, RoomErrorResponse):
        return result.as_http_response()

    identities = None
    if settings.SERVER_ENFORCED_ADMISSION:
        try:
            participant_sids = get_room_participant_sids(session_slug)
        except LiveKitPermissionError as error:
            return _livekit_error(error)
        identities = _project_connected(session_slug, set(participant_sids), user, participant_sids=participant_sids)
        if isinstance(identities, RoomErrorResponse):
            return identities.as_http_response()
        if target is not None and target not in identities:
            return RoomErrorResponse(
                code=ErrorCode.NOT_IN_ROOM, message="Participant is not activated and connected"
            ).as_http_response()
    try:
        action(identities)
    except (LiveKitConfigurationError, LiveKitPermissionError):
        return RoomErrorResponse(
            code=ErrorCode.LIVEKIT_ERROR, message="LiveKit service is not properly configured"
        ).as_http_response()

    return Status(200, None)


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
    return _keeper_livekit_action(
        user,
        session_slug,
        lambda identities: mute_participant(session_slug, participant_identity),
        target=participant_identity,
    )


@router.post(
    "/{session_slug}/disable-camera/{participant_identity}",
    response={200: None, **ERROR_RESPONSES},
    summary="Disable a participant's camera",
    description="Keeper disables a specific participant's camera.",
)
def disable_camera(
    request: HttpRequest,
    session_slug: str,
    participant_identity: str,
):
    user: User = request.user  # type: ignore
    return _keeper_livekit_action(
        user,
        session_slug,
        lambda identities: disable_camera_participant(session_slug, participant_identity),
        target=participant_identity,
    )


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
    return _keeper_livekit_action(
        user,
        session_slug,
        lambda identities: mute_all_participants(
            session_slug,
            except_identity=user.slug,
            **({"identities": identities} if settings.SERVER_ENFORCED_ADMISSION else {}),
        ),
    )


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

    removed_user = User.objects.filter(slug=participant_identity).first()
    if settings.SERVER_ENFORCED_ADMISSION:
        if not removed_user:
            return RoomErrorResponse(
                code=ErrorCode.NOT_JOINABLE, message="Participant is not eligible"
            ).as_http_response()
        from .admission import AdmissionError, record_removal

        try:
            record_removal(
                session_slug,
                user,
                removed_user,
                expected_room_version=result.state_version,
                ban=reason == RemoveReason.BAN,
            )
        except AdmissionError as error:
            code = ErrorCode.NOT_KEEPER if error.code == "not_keeper" else ErrorCode.INVALID_TRANSITION
            return RoomErrorResponse(code=code, message=str(error)).as_http_response()

    try:
        remove_participant(session_slug, participant_identity, reason=reason)
    except LiveKitPermissionError as error:
        if error.code not in {"participant_missing", "room_missing"}:
            return _livekit_error(error)
    except LiveKitConfigurationError as error:
        return _livekit_error(error)

    if removed_user:
        analytics.user_removed_from_room(removed_user, session_slug)

    return Status(200, RemoveParticipantPayload(identity=participant_identity, reason=reason))
