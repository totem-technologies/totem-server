from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field

from totem.rooms.schemas import (
    AdmissionBlockReason,
    AdmissionReadiness,
    AdmissionStateValue,
    AttemptStatusValue,
    RoomState,
    RoomStatus,
)
from totem.users.schemas import PublicUserSchema

AdmissionErrorCode = Literal[
    "not_keeper",
    "not_eligible",
    "permanently_declined",
    "ended",
    "not_found",
    "feature_disabled",
    "stale_version",
    "invalid_attempt",
    "permission_pending",
    "connection_required",
    "command_conflict",
    "admission_full",
    "waiting_full",
    "room_full",
    "presence_unavailable",
    "room_missing",
    "participant_missing",
    "missing",
    "disconnected",
    "identity_replaced",
    "permission_mismatch",
    "unavailable",
    "timeout",
]


class AdmissionRequestInput(Schema):
    request_id: UUID
    attempt_id: UUID
    connected: bool = False


class AttemptReceiptInput(Schema):
    request_id: UUID
    attempt_id: UUID
    expected_version: int = Field(ge=0)


class KeeperDecisionInput(Schema):
    command_id: UUID
    request_id: UUID
    attempt_id: UUID
    expected_version: int = Field(ge=0)
    expected_room_version: int = Field(ge=0)


class DeclineInput(KeeperDecisionInput):
    permanent: bool = False


class MembershipCommandInput(Schema):
    command_id: UUID
    expected_version: int = Field(ge=0)
    expected_room_version: int = Field(ge=0)


class SettingsCommandInput(Schema):
    command_id: UUID
    approval_required: bool
    expected_revision: int = Field(ge=0)
    expected_room_version: int = Field(ge=0)


class BatchCommandInput(Schema):
    command_id: UUID
    expected_room_version: int = Field(ge=0)


class Participant(Schema):
    identity: str
    user: PublicUserSchema
    admission_state: AdmissionStateValue
    admission_version: int
    request_id: UUID | None = None
    attempt_id: UUID | None = None
    attempt_version: int | None = None
    status: Literal[AttemptStatusValue, "no_request", "approved", "activated"]
    requested_at: datetime | None = None
    expires_at: datetime | None = None
    approved_at: datetime | None = None
    activated_at: datetime | None = None
    connected_at: datetime | None = None
    connected: bool | None = None
    connection_state: Literal["connected", "disconnected", "unknown"]
    eligible: bool
    returning: bool
    session_started: bool
    late_arrival: bool
    permission_status: Literal["pending", "in_progress", "error", "applied"]
    permission_revision: int
    applied_permission_revision: int | None = None
    last_error: str | None = None
    next_retry_at: datetime | None = None
    decision_actor: str | None = None
    admission_block_reason: AdmissionBlockReason | None = None
    readiness: AdmissionReadiness | None = None


class AdmissionHeader(Schema):
    session_slug: str
    keeper: str
    room_version: int
    room_state: RoomState
    room_status: RoomStatus
    approval_required: bool
    settings_revision: int
    version: int
    observed_at: datetime
    presence_error: str | None = None
    admitted_recipients: list[str] | None = None
    connected_count: int | None = None
    admitted_count: int
    activated_count: int
    pending_count: int
    admission_capacity: int = 0
    admission_slots_used: int = 0
    waiting_connection_limit: int = 5
    livekit_connection_limit: int = 15
    waiting_slots_used: int | None = None
    connection_slots_used: int | None = None


class AdmissionMeSnapshot(AdmissionHeader):
    me: Participant | None = None
    readiness: AdmissionReadiness


class AdmissionSnapshot(AdmissionHeader):
    participants: list[Participant]
    waiting: list[Participant]
    requests: list[Participant]
    history_truncated: bool


class CommandResult(Schema):
    identity: str | None = None
    request_id: UUID | None = None
    attempt_id: UUID | None = None
    outcome: Literal["approved", "declined", "permanently_declined", "allowed", "revoked", "skipped"]
    error: Literal[AdmissionErrorCode, "requires_reapproval", "approval_required"] | None = None
    participant: Participant | None = None


class AdmissionCommandResponse(Schema):
    command_id: UUID
    replayed: bool
    results: list[CommandResult]
    partial_failure: bool
    snapshot: AdmissionSnapshot


class ErrorSchema(Schema):
    code: AdmissionErrorCode
    message: str
    detail: str | None = None
