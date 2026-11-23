"""Read-only readiness projection from an already-loaded admission snapshot.

This is advisory: reconciliation is a persisted observation, not proof of
current LiveKit presence. Activation still performs its own live verification.
"""

from dataclasses import dataclass
from datetime import datetime

from ..models import AdmissionAttempt, AdmissionPermissionSync, AdmissionState, AttemptStatus, Room, SessionAdmission
from ..schemas import ReadinessReason, ReadinessState


@dataclass(frozen=True)
class ReadinessProjection:
    state: ReadinessState
    reason: ReadinessReason | None = None


def project_readiness(
    room: Room,
    durable: SessionAdmission,
    attempt: AdmissionAttempt | None,
    sync: AdmissionPermissionSync | None,
    eligible: bool,
    capacity: int,
    slots_used: int,
    observed_at: datetime,
    ended: bool,
) -> ReadinessProjection:
    """Project the supplied latest attempt without queries, I/O or mutation.

    All inputs must belong to the same snapshot. The caller must supply the
    latest attempt, not a historical row; this does not validate current presence.
    """
    if ended:
        return ReadinessProjection(ReadinessState.ENDED, ReadinessReason.SESSION_ENDED)
    if not eligible:
        return ReadinessProjection(ReadinessState.BLOCKED, ReadinessReason.NOT_ELIGIBLE)
    keeper = durable.user.slug == room.keeper
    if not keeper:
        if durable.state == AdmissionState.REVOKED:
            return ReadinessProjection(ReadinessState.BLOCKED, ReadinessReason.REQUIRES_REAPPROVAL)
        if durable.state == AdmissionState.PERMANENTLY_DECLINED:
            return ReadinessProjection(ReadinessState.BLOCKED, ReadinessReason.PERMANENTLY_DECLINED)
    if not attempt:
        return ReadinessProjection(ReadinessState.REQUIRES_NEW_ATTEMPT, ReadinessReason.NO_REQUEST)
    if attempt.status in (AttemptStatus.PENDING, AttemptStatus.GRANTING) and attempt.expires_at <= observed_at:
        return ReadinessProjection(ReadinessState.REQUIRES_NEW_ATTEMPT, ReadinessReason.REQUEST_EXPIRED)
    if attempt.status not in (AttemptStatus.PENDING, AttemptStatus.GRANTING, AttemptStatus.ADMITTED):
        reasons = {
            AttemptStatus.DECLINED: ReadinessReason.REQUEST_DECLINED,
            AttemptStatus.PERMANENTLY_DECLINED: ReadinessReason.REQUEST_PERMANENTLY_DECLINED,
            AttemptStatus.CANCELLED: ReadinessReason.REQUEST_CANCELLED,
            AttemptStatus.EXPIRED: ReadinessReason.REQUEST_EXPIRED,
            AttemptStatus.SUPERSEDED: ReadinessReason.REQUEST_SUPERSEDED,
            AttemptStatus.REVOKED: ReadinessReason.REQUEST_REVOKED,
            AttemptStatus.FAILED: ReadinessReason.REQUEST_FAILED,
        }
        return ReadinessProjection(
            ReadinessState.REQUIRES_NEW_ATTEMPT, reasons.get(attempt.status, ReadinessReason.INVALID_REQUEST)
        )

    if not keeper and (slots_used > capacity or (attempt.status == AttemptStatus.PENDING and slots_used >= capacity)):
        return ReadinessProjection(ReadinessState.BLOCKED, ReadinessReason.ADMISSION_FULL)
    if attempt.status == AttemptStatus.PENDING:
        return ReadinessProjection(ReadinessState.WAITING_FOR_APPROVAL, ReadinessReason.APPROVAL_REQUIRED)
    if not keeper and durable.state != AdmissionState.ADMITTED:
        return ReadinessProjection(ReadinessState.BLOCKED, ReadinessReason.NOT_ADMITTED)
    if not attempt.participant_sid or not attempt.connected_at:
        if attempt.status == AttemptStatus.ADMITTED:
            return ReadinessProjection(ReadinessState.REQUIRES_NEW_ATTEMPT, ReadinessReason.CONNECTION_REQUIRED)
        return ReadinessProjection(ReadinessState.APPLYING_PERMISSIONS, ReadinessReason.CONNECTION_REQUIRED)
    if (
        not sync
        or not sync.desired_admitted
        or sync.authority_keeper != room.keeper
        or sync.applied_revision != sync.revision
        or not sync.participant_sid
        or sync.last_error
        or sync.operation_id is not None
        or sync.lease_until is not None
    ):
        return ReadinessProjection(ReadinessState.APPLYING_PERMISSIONS, ReadinessReason.PERMISSION_PENDING)
    if sync.participant_sid != attempt.participant_sid:
        if attempt.status == AttemptStatus.ADMITTED:
            return ReadinessProjection(ReadinessState.REQUIRES_NEW_ATTEMPT, ReadinessReason.CONNECTION_CHANGED)
        return ReadinessProjection(ReadinessState.APPLYING_PERMISSIONS, ReadinessReason.CONNECTION_CHANGED)
    if attempt.status == AttemptStatus.ADMITTED:
        return ReadinessProjection(ReadinessState.ACTIVATED)
    return ReadinessProjection(ReadinessState.READY_TO_ACTIVATE)
