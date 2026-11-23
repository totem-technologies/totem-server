"""Admission application service: HTTP snapshots, idempotent commands and receipts.

Database work uses the existing Session lock. Presence and permission I/O always
happen before/after transactions; packets and participant attributes are hints only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from totem.rooms import admission
from totem.spaces.filters import author_circle_count_prefetch
from totem.spaces.models import Session, Space
from totem.users.models import User
from totem.users.schemas import PublicUserSchema

from ..livekit import (
    ENFORCED_MAX_PARTICIPANTS,
    WAITING_CONNECTION_LIMIT,
    LiveKitPermissionError,
    get_participant_snapshot,
    get_room_participant_sids,
)
from ..models import AdmissionAttempt, AdmissionCommand, AdmissionState, AttemptStatus, Room, SessionAdmission
from ..schemas import AdmissionReadiness, ReadinessReason, ReadinessState, RoomStatus
from . import AdmissionError
from .capacity import admission_limit, admission_slots_used, connection_reservations
from .notifications import bump_admission_version
from .permissions import queue_permission_sync, reconcile_admission_permissions
from .readiness import project_readiness
from .schemas import (
    AdmissionCommandResponse,
    AdmissionHeader,
    AdmissionMeSnapshot,
    AdmissionRequestInput,
    AdmissionSnapshot,
    AttemptReceiptInput,
    BatchCommandInput,
    CommandResult,
    KeeperDecisionInput,
    MembershipCommandInput,
    Participant,
    SettingsCommandInput,
)

CommandInput = KeeperDecisionInput | MembershipCommandInput | SettingsCommandInput | BatchCommandInput
HISTORY_LIMIT = 100


def _read_access(room: Room, actor: User, *, keeper: bool) -> None:
    if not User.objects.filter(pk=actor.pk, is_active=True).exists():
        raise AdmissionError("not_eligible", "Account is inactive")
    if keeper:
        if actor.slug != room.keeper:
            raise AdmissionError("not_keeper", "Only the current Keeper may read the admission queue")
    elif actor.slug != room.keeper and not room.session.attendees.filter(pk=actor.pk).exists():
        raise AdmissionError("not_eligible", "You are not an attendee of this Session")


def _snapshot_room(session_slug: str) -> Room:
    session = Session.objects.select_related("space__author").get(slug=session_slug)
    if session.space.meeting_provider != Space.MeetingProviderChoices.LIVEKIT:
        raise AdmissionError("not_found", "Session not found")
    room = Room.objects.filter(session=session).first()
    if room is None:
        room = Room(session=session, keeper=session.space.author.slug, talking_order=[])
    else:
        room.session = session
    return room


@contextmanager
def _locked_snapshot_session(session_slug: str) -> Iterator[None]:
    Session.objects.select_for_update().get(slug=session_slug)
    yield


@contextmanager
def _authorized_snapshot_room(session_slug: str, actor: User, *, keeper: bool) -> Iterator[Room]:
    room = _snapshot_room(session_slug)
    _read_access(room, actor, keeper=keeper)
    yield room
    _read_access(_snapshot_room(session_slug), actor, keeper=keeper)


def _eligible(room: Room, user: User) -> bool:
    return bool(
        room.status != RoomStatus.ENDED
        and not room.session.cancelled
        and not room.session.ended()
        and admission._eligible(room, user, check_window=False)
    )


def _participant(
    room: Room,
    durable: SessionAdmission,
    attempt: AdmissionAttempt | None,
    connected: set[str] | None,
    capacity: int,
    slots_used: int,
    observed_at: datetime,
    ended: bool,
    attendee_ids: set[int],
    *,
    current: bool = True,
) -> Participant:
    sync = getattr(durable, "permission_sync", None)
    permission_status = "pending"
    if sync:
        if sync.operation_id is not None:
            permission_status = "in_progress"
        elif sync.last_error:
            permission_status = "error"
        elif sync.applied_revision == sync.revision:
            permission_status = "applied"
    status = attempt.status if attempt else "no_request"
    if attempt and status in admission.ACTIVE_STATUSES:
        if ended:
            status = AttemptStatus.CANCELLED
        elif attempt.expires_at <= observed_at:
            status = AttemptStatus.EXPIRED
    if status == AttemptStatus.GRANTING and permission_status == "applied" and sync and sync.desired_admitted:
        status = "approved"
    elif status == AttemptStatus.ADMITTED:
        status = (
            durable.state
            if durable.state in [AdmissionState.REVOKED, AdmissionState.PERMANENTLY_DECLINED]
            else "activated"
        )
    present = durable.user.slug in connected if connected is not None else None
    decision_actor = attempt.decision_actor if attempt and attempt.decision_actor_id else durable.decision_actor
    block_reason = None
    if durable.user.slug != room.keeper:
        if durable.state == AdmissionState.REVOKED:
            block_reason = "requires_reapproval"
        elif durable.state == AdmissionState.PERMANENTLY_DECLINED:
            block_reason = "permanently_declined"
        elif slots_used > capacity or (status == AttemptStatus.PENDING and slots_used >= capacity):
            block_reason = "admission_full"
    eligible = bool(
        not ended
        and durable.user.is_authenticated
        and durable.user.is_active
        and durable.user.slug not in room.banned_participants
        and durable.user_id in attendee_ids
    )
    readiness = (
        project_readiness(room, durable, attempt, sync, eligible, capacity, slots_used, observed_at, ended)
        if current
        else None
    )
    return Participant(
        identity=durable.user.slug,
        user=PublicUserSchema.model_validate(durable.user),
        admission_state=durable.state,
        admission_version=durable.version,
        request_id=attempt.request_id if attempt else None,
        attempt_id=attempt.attempt_id if attempt else None,
        attempt_version=attempt.version if attempt else None,
        status=status,
        requested_at=attempt.date_created if attempt else None,
        expires_at=attempt.expires_at if attempt else None,
        approved_at=attempt.decided_at
        if attempt and (attempt.status == AttemptStatus.ADMITTED or status in [AttemptStatus.GRANTING, "approved"])
        else None,
        activated_at=attempt.completed_at if attempt and attempt.status == AttemptStatus.ADMITTED else None,
        connected_at=attempt.connected_at if attempt else None,
        connected=present,
        connection_state="unknown" if present is None else "connected" if present else "disconnected",
        eligible=eligible,
        returning=attempt.returning if attempt else False,
        session_started=attempt.session_started if attempt else False,
        late_arrival=bool(attempt and attempt.session_started and not attempt.returning),
        permission_status=permission_status,
        permission_revision=sync.revision if sync else 0,
        applied_permission_revision=sync.applied_revision if sync else None,
        last_error=sync.last_error or None if sync else None,
        next_retry_at=sync.next_retry_at if sync else None,
        decision_actor=decision_actor.slug if decision_actor else None,
        admission_block_reason=block_reason,
        readiness=AdmissionReadiness(state=readiness.state, reason=readiness.reason) if readiness else None,
    )


def admission_snapshot(
    session_slug: str, actor: User, *, keeper: bool = True
) -> AdmissionSnapshot | AdmissionMeSnapshot:
    # Authorize before I/O, and again before exposing a snapshot after I/O.
    with _authorized_snapshot_room(session_slug, actor, keeper=keeper):
        pass
    presence_error = None
    try:
        participant_sids: dict[str, str] | None = get_room_participant_sids(session_slug)
    except LiveKitPermissionError as error:
        participant_sids = None
        presence_error = error.code
    observed_at = timezone.now()
    connected = set(participant_sids) if participant_sids is not None else None
    # All cooperating room/admission writers take this lock. Presence is an
    # independent observation made before the lock, never a database guarantee.
    with (
        transaction.atomic(),
        _locked_snapshot_session(session_slug),
        _authorized_snapshot_room(session_slug, actor, keeper=keeper) as room,
    ):
        ended = room.status == RoomStatus.ENDED or room.session.cancelled or room.session.ended()
        memberships = list(
            room.session.admissions.select_related("user", "decision_actor", "permission_sync").prefetch_related(
                author_circle_count_prefetch("user")
            )
        )
        attempts = AdmissionAttempt.objects.filter(admission__session=room.session).select_related("decision_actor")
        latest = {
            attempt.admission_id: attempt
            for attempt in attempts.order_by("admission_id", "-date_created", "-pk").distinct("admission_id")
        }
        by_id = {item.pk: item for item in memberships}
        capacity = admission_limit(room)
        slots_used = admission_slots_used(room)
        attendees = list(room.session.attendees.values_list("pk", "slug"))
        attendee_ids = {pk for pk, _ in attendees}
        participants = [
            _participant(
                room, item, latest.get(item.pk), connected, capacity, slots_used, observed_at, ended, attendee_ids
            )
            for item in memberships
        ]
        participant_rows = [item for item in participants if item.identity != room.keeper]
        waiting = sorted(
            [item for item in participant_rows if item.status == AttemptStatus.PENDING],
            key=lambda item: cast(datetime, item.requested_at),
        )
        identities = {slug for _, slug in attendees} | {room.keeper}

        occupied, waiting_slots = connection_reservations(room, connected) if connected is not None else (None, None)
        recipients = None
        if participant_sids is not None:
            recipients = sorted(
                {
                    item.identity
                    for membership, item in zip(memberships, participants, strict=True)
                    if item.identity != room.keeper
                    and item.admission_state == AdmissionState.ADMITTED
                    and item.status == "activated"
                    and item.eligible
                    and (attempt := latest.get(membership.pk)) is not None
                    and bool(attempt.participant_sid)
                    and participant_sids.get(item.identity) == attempt.participant_sid
                }
                | ({room.keeper} if room.keeper in participant_sids else set())
            )
        header = AdmissionHeader(
            session_slug=session_slug,
            keeper=room.keeper,
            room_version=room.state_version,
            room_state=room.to_state(),
            room_status=room.status,
            approval_required=room.approval_required,
            settings_revision=room.admission_revision,
            version=room.admission_version,
            observed_at=observed_at,
            presence_error=presence_error,
            admitted_recipients=recipients,
            connected_count=len(connected & identities) if connected is not None else None,
            admitted_count=sum(
                item.admission_state == AdmissionState.ADMITTED and item.eligible for item in participant_rows
            ),
            activated_count=sum(item.status == "activated" and item.eligible for item in participant_rows),
            pending_count=sum(item.eligible for item in waiting),
            admission_capacity=capacity,
            admission_slots_used=slots_used,
            waiting_connection_limit=WAITING_CONNECTION_LIMIT,
            livekit_connection_limit=ENFORCED_MAX_PARTICIPANTS,
            waiting_slots_used=len(waiting_slots) if waiting_slots is not None else None,
            connection_slots_used=len(occupied | {room.keeper}) if occupied is not None else None,
        )
        if not keeper:
            me = next((item for item in participants if item.identity == actor.slug), None)
            readiness = me.readiness if me else None
            if readiness is None:
                readiness = AdmissionReadiness(
                    state=ReadinessState.ENDED if ended else ReadinessState.REQUIRES_NEW_ATTEMPT,
                    reason=ReadinessReason.SESSION_ENDED if ended else ReadinessReason.NO_REQUEST,
                )
            return AdmissionMeSnapshot(**header.model_dump(), me=me, readiness=readiness)
        recent = list(attempts.order_by("-date_created", "-pk")[: HISTORY_LIMIT + 1])
        history = [
            _participant(
                room,
                by_id[item.admission_id],
                item,
                connected,
                capacity,
                slots_used,
                observed_at,
                ended,
                attendee_ids,
                current=latest.get(item.admission_id) is not None and latest[item.admission_id].pk == item.pk,
            )
            for item in reversed(recent[:HISTORY_LIMIT])
        ]
        return AdmissionSnapshot(
            **header.model_dump(),
            participants=participants,
            waiting=waiting,
            requests=history,
            history_truncated=len(recent) > HISTORY_LIMIT,
        )


def _owned_attempt(room: Room, user: User, request_id: UUID, attempt_id: UUID) -> AdmissionAttempt:
    attempt = admission._attempt(room, request_id, attempt_id)
    if attempt.admission.user_id != user.pk:
        raise AdmissionError("invalid_attempt", "Attempt belongs to another identity")
    latest = attempt.admission.attempts.order_by("-date_created", "-pk").first()
    if not latest or latest.pk != attempt.pk:
        raise AdmissionError("invalid_attempt", "A newer connection attempt superseded this request")
    return attempt


def confirm_connection(session_slug: str, user: User, request_id: UUID, attempt_id: UUID) -> AdmissionAttempt:
    with admission._locked_room(session_slug) as room:
        admission._require_open(room)
        if not _eligible(room, user):
            raise AdmissionError("not_eligible", "You are no longer an eligible attendee")
        attempt = _owned_attempt(room, user, request_id, attempt_id)
        if attempt.status not in [AttemptStatus.PENDING, AttemptStatus.GRANTING, AttemptStatus.ADMITTED]:
            raise AdmissionError("invalid_attempt", "This attempt cannot connect")
        if attempt.admission.state == AdmissionState.PERMANENTLY_DECLINED and user.slug != room.keeper:
            raise AdmissionError("permanently_declined", "Admission is permanently declined")
        previous_sid = attempt.participant_sid
    participant = get_participant_snapshot(session_slug, user.slug)
    if participant.identity != user.slug:
        raise LiveKitPermissionError("identity_replaced", "LiveKit identity does not match the authenticated user")
    with admission._locked_room(session_slug) as room:
        admission._require_open(room)
        if not _eligible(room, user):
            raise AdmissionError("not_eligible", "You are no longer an eligible attendee")
        attempt = _owned_attempt(room, user, request_id, attempt_id)
        if attempt.status not in [AttemptStatus.PENDING, AttemptStatus.GRANTING, AttemptStatus.ADMITTED]:
            raise AdmissionError("invalid_attempt", "Attempt changed while checking presence")
        if attempt.admission.state == AdmissionState.PERMANENTLY_DECLINED and user.slug != room.keeper:
            raise AdmissionError("permanently_declined", "Admission changed while checking presence")
        if attempt.status == AttemptStatus.ADMITTED and attempt.participant_sid != participant.sid:
            raise AdmissionError("invalid_attempt", "A replacement connection needs a fresh admission attempt")
        if attempt.participant_sid not in [previous_sid, participant.sid]:
            raise AdmissionError("stale_version", "A newer connection receipt superseded this observation")
        queued_sync = attempt.participant_sid != participant.sid
        if queued_sync:
            attempt.participant_sid = participant.sid
            attempt.connected_at = timezone.now()
            attempt.version += 1
            attempt.save(update_fields=["participant_sid", "connected_at", "version", "date_modified"])
            bump_admission_version(room.session_id, user.slug)
            queue_permission_sync(attempt.admission)
        admission_id = attempt.admission_id
    if not queued_sync:
        # A same-SID retry respects the shared backoff and never creates a new grant.
        reconcile_admission_permissions(admission_id)
    return attempt


def request_admission_http(session_slug: str, user: User, body: AdmissionRequestInput) -> AdmissionMeSnapshot:
    if body.connected:
        confirm_connection(session_slug, user, body.request_id, body.attempt_id)
    else:
        with admission._locked_room(session_slug) as room:
            admission._require_open(room)
            if not _eligible(room, user):
                raise AdmissionError("not_eligible", "You are not an eligible attendee")
            attempt = admission.request_admission(session_slug, user, body.request_id, body.attempt_id)
            _owned_attempt(room, user, body.request_id, body.attempt_id)
            # Duplicate terminal requests are observable, never reopened.
            if attempt.admission.state == AdmissionState.PERMANENTLY_DECLINED and user.slug != room.keeper:
                raise AdmissionError("permanently_declined", "Admission is permanently declined")
    return cast(AdmissionMeSnapshot, admission_snapshot(session_slug, user, keeper=False))


def activate_admission_http(session_slug: str, user: User, body: AttemptReceiptInput) -> AdmissionMeSnapshot:
    with admission._locked_room(session_slug) as room:
        admission._require_open(room)
        attempt = _owned_attempt(room, user, body.request_id, body.attempt_id)
        if not attempt.connected_at or not attempt.participant_sid:
            raise AdmissionError("connection_required", "Confirm this connection before activation")
    admission.complete_admission(
        session_slug, user, body.request_id, body.attempt_id, expected_version=body.expected_version
    )
    return cast(AdmissionMeSnapshot, admission_snapshot(session_slug, user, keeper=False))


def cancel_admission_http(session_slug: str, user: User, body: AttemptReceiptInput) -> AdmissionMeSnapshot:
    admission.cancel_admission(
        session_slug, user, body.request_id, body.attempt_id, expected_version=body.expected_version
    )
    return cast(AdmissionMeSnapshot, admission_snapshot(session_slug, user, keeper=False))


def _target(room: Room, identity: str) -> User:
    if identity == room.keeper:
        raise AdmissionError("not_eligible", "The Keeper cannot decide their own admission")
    user = User.objects.filter(slug=identity, is_active=True, pk__in=room.session.attendees.values("pk")).first()
    if not user:
        raise AdmissionError("not_eligible", "Target is not an eligible participant in this Session")
    return user


def _result(attempt: AdmissionAttempt, outcome: str, error: str | None = None) -> dict[str, Any]:
    return dict(
        identity=attempt.admission.user.slug,
        request_id=str(attempt.request_id),
        attempt_id=str(attempt.attempt_id),
        outcome=outcome,
        error=error,
    )


def _batch(room: Room, actor: User) -> list[dict[str, Any]]:
    results = []
    for attempt in (
        AdmissionAttempt.objects.filter(admission__session=room.session, status=AttemptStatus.PENDING)
        .select_related("admission__user")
        .order_by("date_created", "pk")
    ):
        try:
            admission.decide_admission(
                room.session.slug,
                actor,
                attempt.request_id,
                attempt.attempt_id,
                "approve",
                expected_version=attempt.version,
                expected_room_version=room.state_version,
            )
        except AdmissionError as error:
            results.append(_result(attempt, "skipped", error.code))
        else:
            results.append(_result(attempt, "approved"))
    return results


def _apply_command(
    room: Room, actor: User, action: str, body: CommandInput, identity: str | None
) -> list[dict[str, Any]]:
    if action == "admit_all":
        return _batch(room, actor)
    if action == "settings" and isinstance(body, SettingsCommandInput):
        pending = list(
            AdmissionAttempt.objects.filter(
                admission__session=room.session, status=AttemptStatus.PENDING
            ).select_related("admission__user")
        )
        outcomes: dict[int, tuple[AdmissionAttempt, str | None]] = {}
        admission.update_approval_required(
            room.session.slug,
            actor,
            body.approval_required,
            expected_revision=body.expected_revision,
            expected_room_version=body.expected_room_version,
            outcomes=outcomes,
        )
        if body.approval_required:
            return []
        results = []
        for original in pending:
            attempt, error = outcomes.get(original.pk, (original, "invalid_attempt"))
            results.append(_result(attempt, "approved" if error is None else "skipped", error))
        return results
    if identity is None:
        raise AdmissionError("invalid_attempt", "A target identity is required")
    target = _target(room, identity)
    if action in ["approve", "decline", "permanentdecline"] and isinstance(body, KeeperDecisionInput):
        attempt = admission._attempt(room, body.request_id, body.attempt_id)
        if attempt.admission.user_id != target.pk:
            raise AdmissionError("invalid_attempt", "The request does not belong to the target identity")
        decision = "permanently_decline" if action == "permanentdecline" else action
        attempt = admission.decide_admission(
            room.session.slug,
            actor,
            body.request_id,
            body.attempt_id,
            decision,
            expected_version=body.expected_version,
            expected_room_version=body.expected_room_version,
        )
        outcome = {"approve": "approved", "decline": "declined", "permanentdecline": "permanently_declined"}[action]
        return [_result(attempt, outcome)]
    if action in ["allow", "revoke"] and isinstance(body, MembershipCommandInput):
        operation = admission.allow_previously_declined if action == "allow" else admission.revoke_admission
        operation(
            room.session.slug,
            actor,
            target,
            expected_version=body.expected_version,
            expected_room_version=body.expected_room_version,
        )
        return [dict(identity=identity, outcome="allowed" if action == "allow" else "revoked", error=None)]
    raise AdmissionError("invalid_attempt", "Unknown admission command")


def execute_keeper_command(
    session_slug: str, actor: User, action: str, body: CommandInput, identity: str | None = None
) -> AdmissionCommandResponse:
    payload = dict(action=action, identity=identity, body=body.model_dump(mode="json", exclude={"command_id"}))
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with admission._locked_room(session_slug) as room:
        # Authenticate the current Keeper before replay, but don't reapply old
        # optimistic versions to a receipt for an already committed command.
        admission._keeper(room, actor, room.state_version)
        receipt = AdmissionCommand.objects.filter(session=room.session, command_id=body.command_id).first()
        replayed = receipt is not None
        if receipt:
            if receipt.actor_id != actor.pk or receipt.action != action or receipt.payload_hash != fingerprint:
                raise AdmissionError(
                    "command_conflict", "This command ID was already used for another payload or actor"
                )
            rows = receipt.result
        else:
            admission._version(room.state_version, body.expected_room_version)
            rows = _apply_command(room, actor, action, body, identity)
            AdmissionCommand.objects.create(
                session=room.session,
                actor=actor,
                command_id=body.command_id,
                action=action,
                payload_hash=fingerprint,
                result=rows,
            )
    # on_commit permission operations have finished or left durable pending/error
    # state. Never report a blanket batch success from the DB decision alone.
    snapshot = cast(AdmissionSnapshot, admission_snapshot(session_slug, actor))
    participants: dict[str | None, Participant] = {item.identity: item for item in snapshot.participants}
    results = [CommandResult(**row, participant=participants.get(row.get("identity"))) for row in rows]
    partial_failure = any(
        item.error or (item.participant and item.participant.permission_status != "applied") for item in results
    )
    return AdmissionCommandResponse(
        command_id=body.command_id,
        replayed=replayed,
        results=results,
        partial_failure=partial_failure,
        snapshot=snapshot,
    )
