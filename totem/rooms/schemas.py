"""
Shared types for the rooms app.

This module is the leaf of the dependency graph — it imports nothing
from the rest of the app. Everything else imports from here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from ninja import Field, Schema, Status
from pydantic import ConfigDict

MAX_PROMPT_LENGTH = 2000

AdmissionStateValue = Literal["none", "admitted", "permanently_declined", "revoked"]
AttemptStatusValue = Literal[
    "pending",
    "granting",
    "admitted",
    "declined",
    "permanently_declined",
    "cancelled",
    "expired",
    "superseded",
    "revoked",
    "failed",
]
AdmissionBlockReason = Literal["requires_reapproval", "permanently_declined", "admission_full"]
PermissionErrorCode = Literal[
    "room_missing",
    "participant_missing",
    "unavailable",
    "timeout",
    "identity_replaced",
    "permission_mismatch",
    "stale_operation",
    "lease_recovered",
    "permission_pending",
]

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReadinessState(StrEnum):
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPLYING_PERMISSIONS = "applying_permissions"
    READY_TO_ACTIVATE = "ready_to_activate"
    ACTIVATED = "activated"
    BLOCKED = "blocked"
    ENDED = "ended"
    REQUIRES_NEW_ATTEMPT = "requires_new_attempt"


class ReadinessReason(StrEnum):
    SESSION_ENDED = "session_ended"
    NOT_ELIGIBLE = "not_eligible"
    NO_REQUEST = "no_request"
    REQUEST_EXPIRED = "request_expired"
    REQUEST_DECLINED = "request_declined"
    REQUEST_PERMANENTLY_DECLINED = "request_permanently_declined"
    REQUEST_CANCELLED = "request_cancelled"
    REQUEST_SUPERSEDED = "request_superseded"
    REQUEST_REVOKED = "request_revoked"
    REQUEST_FAILED = "request_failed"
    INVALID_REQUEST = "invalid_request"
    REQUIRES_REAPPROVAL = "requires_reapproval"
    PERMANENTLY_DECLINED = "permanently_declined"
    NOT_ADMITTED = "not_admitted"
    ADMISSION_FULL = "admission_full"
    APPROVAL_REQUIRED = "approval_required"
    CONNECTION_REQUIRED = "connection_required"
    PERMISSION_PENDING = "permission_pending"
    CONNECTION_CHANGED = "connection_changed"


class AdmissionReadiness(Schema):
    state: ReadinessState
    reason: ReadinessReason | None = None


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
    BANNED = "banned"

    # Invalid state transitions
    INVALID_TRANSITION = "invalid_transition"
    ROOM_NOT_ACTIVE = "room_not_active"
    ROOM_NOT_WAITING = "room_not_waiting"
    ROOM_ALREADY_ENDED = "room_already_ended"

    # Data validation
    INVALID_PARTICIPANT_ORDER = "invalid_participant_order"
    KEEPER_NOT_IN_ROOM = "keeper_not_in_room"

    # Concurrency
    STALE_VERSION = "stale_version"

    # Join
    NOT_JOINABLE = "not_joinable"
    ADMISSION_FULL = "admission_full"
    WAITING_ROOM_FULL = "waiting_full"
    ROOM_FULL = "room_full"

    # LiveKit
    LIVEKIT_ERROR = "livekit_error"

    # Generic
    NOT_FOUND = "not_found"


class EndReason(str, Enum):
    KEEPER_ENDED = "keeper_ended"
    KEEPER_ABSENT = "keeper_absent"
    ROOM_EMPTY = "room_empty"


class RemoveReason(str, Enum):
    REMOVE = "remove"
    BAN = "ban"


# ---------------------------------------------------------------------------
# LiveKit data message payloads
# ---------------------------------------------------------------------------


class RemoveParticipantPayload(Schema):
    action: Literal["remove_participant"] = "remove_participant"
    identity: str
    reason: RemoveReason


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
    banned_participants: list[str] = []  # user slugs
    round_number: int
    round_message: Optional[str] = None
    round_prompt_id: int | None = None


# ---------------------------------------------------------------------------
# Event schemas (discriminated union on `type`)
# ---------------------------------------------------------------------------


class StartRoomEvent(Schema):
    type: Literal["start_room"] = "start_room"
    prompt: Optional[str] = Field(None, max_length=MAX_PROMPT_LENGTH)


class PassStickEvent(Schema):
    type: Literal["pass_stick"] = "pass_stick"
    prompt: Optional[str] = Field(None, max_length=MAX_PROMPT_LENGTH)
    session_prompt_id: int | None = Field(None, ge=1)


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


class SetPromptEvent(Schema):
    """Keeper sets or replaces the active round prompt during a live session."""

    type: Literal["set_prompt"] = "set_prompt"
    prompt: Optional[str] = Field(None, max_length=MAX_PROMPT_LENGTH)
    session_prompt_id: int | None = Field(None, ge=1)


class EndRoomEvent(Schema):
    type: Literal["end_room"] = "end_room"
    reason: EndReason


class BanParticipantEvent(Schema):
    """Keeper permanently bans a participant, removing them from the talking order."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["ban_participant"] = "ban_participant"
    participant_slug: str = Field(alias="participantSlug")


class UnbanParticipantEvent(Schema):
    """Keeper lifts a ban, allowing the participant to rejoin."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["unban_participant"] = "unban_participant"
    participant_slug: str = Field(alias="participantSlug")


class EmptyRoomEvent(Schema):
    """Server-internal event for reconciling state with LiveKit presence."""

    type: Literal["empty"] = "empty"


RoomEvent = Annotated[
    Union[
        StartRoomEvent,
        PassStickEvent,
        AcceptStickEvent,
        ForcePassStickEvent,
        ReorderEvent,
        SetPromptEvent,
        EndRoomEvent,
        BanParticipantEvent,
        UnbanParticipantEvent,
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


class AdmissionJoinRequest(Schema):
    """An operation resumes an active attempt by default; fresh starts a new one.

    A returning admitted user resumes when connected, otherwise starts a new
    attempt. Retry with the same operation ID and fresh value. Alternatively
    supply both legacy request/attempt IDs. The response contains canonical IDs.
    """

    operation_id: UUID | None = None
    fresh: bool = False
    request_id: UUID | None = None
    attempt_id: UUID | None = None


class AdmissionJoinState(Schema):
    request_id: UUID
    attempt_id: UUID
    status: AttemptStatusValue
    durable_state: AdmissionStateValue
    approval_required: bool
    expires_at: datetime
    permissions: Literal["waiting", "admitted"]
    permission_sync: Literal["pending", "applied", PermissionErrorCode]
    revision: int
    admission_block_reason: AdmissionBlockReason | None = None
    observed_at: datetime
    readiness: AdmissionReadiness


class JoinResponse(Schema):
    """Token and server-owned admission snapshot (absent during legacy rollout)."""

    token: str
    is_already_present: bool
    admission: AdmissionJoinState | None = None


class RoomErrorResponse(Schema):
    """
    Structured error. Clients switch on `code`, display `message`.
    `detail` is optional extra context for debugging.
    """

    code: ErrorCode
    message: str
    detail: Optional[str] = None

    def as_http_response(self) -> Status[RoomErrorResponse]:
        """Map error codes to HTTP statuses. Defaults to 400."""
        match self.code:
            case (
                ErrorCode.NOT_IN_ROOM
                | ErrorCode.NOT_KEEPER
                | ErrorCode.NOT_CURRENT_SPEAKER
                | ErrorCode.NOT_NEXT_SPEAKER
                | ErrorCode.NOT_JOINABLE
                | ErrorCode.BANNED
                | ErrorCode.ROOM_ALREADY_ENDED
            ):
                return Status(403, self)
            case ErrorCode.NOT_FOUND:
                return Status(404, self)
            case ErrorCode.STALE_VERSION | ErrorCode.ADMISSION_FULL | ErrorCode.WAITING_ROOM_FULL | ErrorCode.ROOM_FULL:
                return Status(409, self)
            case ErrorCode.LIVEKIT_ERROR:
                return Status(500, self)
            case _:
                return Status(400, self)


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
