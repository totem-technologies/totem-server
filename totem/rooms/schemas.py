"""
Shared types for the rooms app.

This module is the leaf of the dependency graph — it imports nothing
from the rest of the app. Everything else imports from here.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional, Union

from ninja import Field, Schema

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RoomStatus(str, Enum):
    WAITING_ROOM = "waiting_room"
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
    NOT_IN_ROOM = "not_in_room"
    NOT_KEEPER = "not_keeper"
    NOT_CURRENT_SPEAKER = "not_current_speaker"
    NOT_NEXT_SPEAKER = "not_next_speaker"

    # Invalid state transitions
    INVALID_TRANSITION = "invalid_transition"
    ROOM_NOT_ACTIVE = "room_not_active"
    ROOM_NOT_WAITING = "room_not_waiting"
    ROOM_ALREADY_ENDED = "room_already_ended"

    # Data validation
    INVALID_PARTICIPANT_ORDER = "invalid_participant_order"

    # Concurrency
    STALE_VERSION = "stale_version"

    # Join
    NOT_JOINABLE = "not_joinable"

    # LiveKit
    LIVEKIT_ERROR = "livekit_error"

    # Generic
    NOT_FOUND = "not_found"


class EndReason(str, Enum):
    KEEPER_ENDED = "keeper_ended"
    KEEPER_ABSENT = "keeper_absent"
    ROOM_EMPTY = "room_empty"


# ---------------------------------------------------------------------------
# Status detail (discriminated union)
# ---------------------------------------------------------------------------


class WaitingRoomDetail(Schema):
    type: Literal["waiting_room"] = "waiting_room"


class ActiveDetail(Schema):
    type: Literal["active"] = "active"


class EndedDetail(Schema):
    type: Literal["ended"] = "ended"
    reason: EndReason


StatusDetail = Annotated[
    Union[WaitingRoomDetail, ActiveDetail, EndedDetail],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------


class RoomState(Schema):
    """
    The canonical state snapshot. This is what gets:
    - returned from both endpoints
    - published to LiveKit room metadata
    - built from the Room model

    Clients should treat this as the single type they deserialize everywhere.
    User references are slugs (short unique public IDs), not internal IDs.
    """

    session_slug: str
    version: int
    status: RoomStatus
    turn_state: TurnState
    status_detail: StatusDetail
    current_speaker: Optional[str] = None  # user slug
    next_speaker: Optional[str] = None  # user slug
    talking_order: list[str]  # user slugs
    keeper: str  # user slug


# ---------------------------------------------------------------------------
# Event schemas (discriminated union on `type`)
# ---------------------------------------------------------------------------


class StartRoomEvent(Schema):
    type: Literal["start_room"] = "start_room"


class PassStickEvent(Schema):
    type: Literal["pass_stick"] = "pass_stick"


class AcceptStickEvent(Schema):
    type: Literal["accept_stick"] = "accept_stick"


class ForcePassStickEvent(Schema):
    """
    Keeper forces the current speaker to pass the stick.
    The next speaker won't have a chance to accept — the stick will be passed immediately.
    """

    type: Literal["force_pass_stick"] = "force_pass_stick"


class ReorderEvent(Schema):
    """Keeper reorders the talking order."""

    type: Literal["reorder"] = "reorder"
    talking_order: list[str]  # user slugs


class EndRoomEvent(Schema):
    type: Literal["end_room"] = "end_room"
    reason: EndReason


RoomEvent = Annotated[
    Union[
        StartRoomEvent,
        PassStickEvent,
        AcceptStickEvent,
        ForcePassStickEvent,
        ReorderEvent,
        EndRoomEvent,
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

    event: RoomEvent
    last_seen_version: int


class JoinResponse(Schema):
    """Token for connecting to a LiveKit room."""

    token: str


class ErrorResponse(Schema):
    """
    Structured error. Clients switch on `code`, display `message`.
    `detail` is optional extra context for debugging.
    """

    code: ErrorCode
    message: str
    detail: Optional[str] = None

    def as_http_response(self) -> tuple[int, ErrorResponse]:
        """Map error codes to HTTP statuses. Defaults to 400."""
        match self.code:
            case (
                ErrorCode.NOT_IN_ROOM
                | ErrorCode.NOT_KEEPER
                | ErrorCode.NOT_CURRENT_SPEAKER
                | ErrorCode.NOT_NEXT_SPEAKER
                | ErrorCode.NOT_JOINABLE
            ):
                return 403, self
            case ErrorCode.NOT_FOUND:
                return 404, self
            case ErrorCode.STALE_VERSION:
                return 409, self
            case ErrorCode.LIVEKIT_ERROR:
                return 500, self
            case _:
                return 400, self


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


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
