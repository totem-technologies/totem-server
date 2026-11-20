"""Server-owned admission policy. All writes serialize on the Session row.

LiveKit permission I/O is scheduled after commit; JWT signing is local and runs
under the Session lock. Callers must authenticate users; Keeper commands also
fence against the current Room state version.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from totem.spaces.models import Session
from totem.users.models import User

from ..models import AdmissionAttempt, AdmissionState, AttemptStatus, Room, SessionAdmission
from ..schemas import RoomStatus
from .notifications import bump_admission_version

if TYPE_CHECKING:
    from ..schemas import JoinResponse

ACTIVE_STATUSES = [AttemptStatus.PENDING, AttemptStatus.GRANTING]


class AdmissionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@contextmanager
def _locked_room(session_slug: str) -> Iterator[Room]:
    error: AdmissionError | None = None
    with transaction.atomic():
        session = Session.objects.select_for_update().get(slug=session_slug)
        room = Room.objects.get_or_create_for_session(session)
        room.session = session
        _expire_attempts(room)
        try:
            # Rejected commands roll back, but expiry discovered under the lock persists.
            with transaction.atomic():
                yield room
        except AdmissionError as rejected:
            error = rejected
    if error is not None:
        raise error


def invalidate_pending_admission(session: Session) -> None:
    """Invalidate outstanding attempts. Caller must hold the Session lock."""
    _finish_attempts(
        AdmissionAttempt.objects.filter(admission__session=session, status__in=ACTIVE_STATUSES),
        AttemptStatus.CANCELLED,
    )
    if settings.SERVER_ENFORCED_ADMISSION:
        from .permissions import queue_permission_sync

        for admission in session.admissions.select_related("permission_sync"):
            sync = getattr(admission, "permission_sync", None)
            if sync is None or sync.desired_admitted:
                queue_permission_sync(admission)


def _finish_attempts(attempts: QuerySet[AdmissionAttempt], status: AttemptStatus, *, schedule: bool = True) -> None:
    for attempt in attempts:
        _set_attempt(attempt, status, schedule=schedule)


def _expire_attempts(room: Room) -> None:
    if room.status == RoomStatus.ENDED or room.session.cancelled or room.session.ended():
        invalidate_pending_admission(room.session)
    else:
        _finish_attempts(
            AdmissionAttempt.objects.filter(
                admission__session=room.session, status__in=ACTIVE_STATUSES, expires_at__lte=timezone.now()
            ),
            AttemptStatus.EXPIRED,
        )


def _require_open(room: Room) -> None:
    if room.status == RoomStatus.ENDED or room.session.ended():
        raise AdmissionError("ended", "The session has ended")
    if room.session.cancelled:
        raise AdmissionError("not_eligible", "The session is cancelled")


def _eligible(room: Room, user: User, *, check_window: bool = True) -> bool:
    return (
        user.is_authenticated
        and user.is_active
        and user.slug not in room.banned_participants
        and room.session.attendees.filter(pk=user.pk).exists()
        and (not check_window or room.session.can_join(user))
    )


def _keeper(room: Room, actor: User, expected_room_version: int) -> None:
    _require_open(room)
    if not actor.is_active or actor.slug != room.keeper:
        raise AdmissionError("not_keeper", "Only the current Keeper may decide admission")
    _version(room.state_version, expected_room_version)


def _version(current: int, expected: int) -> None:
    if current != expected:
        raise AdmissionError("stale_version", "State changed; reload before retrying")


def _set_membership(
    admission: SessionAdmission, state: AdmissionState, actor: User | None, *, schedule: bool = True
) -> None:
    admission.state = state
    admission.version += 1
    admission.decision_actor = actor
    admission.decided_at = timezone.now()
    admission.save()
    bump_admission_version(admission.session_id, admission.user.slug, notify=schedule)
    if schedule:
        _queue_permissions(admission)


def _queue_permissions(admission: SessionAdmission) -> None:
    if settings.SERVER_ENFORCED_ADMISSION:
        from .permissions import queue_permission_sync

        queue_permission_sync(admission)


def _set_attempt(
    attempt: AdmissionAttempt, status: AttemptStatus, actor: User | None = None, *, schedule: bool = True
) -> None:
    attempt.status = status
    attempt.version += 1
    if status in [AttemptStatus.GRANTING, AttemptStatus.DECLINED, AttemptStatus.PERMANENTLY_DECLINED]:
        attempt.decision_actor = actor
        attempt.decided_at = timezone.now()
    if status not in ACTIVE_STATUSES:
        attempt.completed_at = timezone.now()
    attempt.save()
    bump_admission_version(attempt.admission.session_id, attempt.admission.user.slug, notify=schedule)
    if schedule and status != AttemptStatus.ADMITTED:
        _queue_permissions(attempt.admission)


def _approve(attempt: AdmissionAttempt, actor: User | None, *, record_admission: bool = True) -> None:
    if settings.SERVER_ENFORCED_ADMISSION:
        from .capacity import ensure_admission_capacity

        room = Room.objects.select_related("session").get(session_id=attempt.admission.session_id)
        ensure_admission_capacity(room, attempt.admission.user)
    if record_admission:
        _set_membership(attempt.admission, AdmissionState.ADMITTED, actor, schedule=False)
    attempt.session_started = Room.objects.filter(
        session_id=attempt.admission.session_id, status=RoomStatus.ACTIVE
    ).exists()
    attempt.expires_at = min(attempt.expires_at, timezone.now() + timedelta(minutes=2))
    _set_attempt(attempt, AttemptStatus.GRANTING, actor)


def _automatic_approval(room: Room, attempt: AdmissionAttempt, actor: User | None = None) -> bool:
    member = attempt.admission
    keeper = member.user.slug == room.keeper
    removed = settings.SERVER_ENFORCED_ADMISSION and member.state == AdmissionState.REVOKED
    if not keeper and (removed or member.state == AdmissionState.PERMANENTLY_DECLINED):
        return False
    if not keeper and room.approval_required and member.state != AdmissionState.ADMITTED:
        return False
    try:
        _approve(attempt, actor, record_admission=not keeper)
    except AdmissionError as error:
        if error.code != "admission_full":
            raise
        return False
    return True


def request_admission(session_slug: str, user: User, request_id: UUID, attempt_id: UUID) -> AdmissionAttempt:
    with _locked_room(session_slug) as room:
        _require_open(room)
        existing = AdmissionAttempt.objects.filter(Q(request_id=request_id) | Q(attempt_id=attempt_id)).first()
        if existing:
            if (
                existing.admission.session_id != room.session_id
                or existing.admission.user_id != user.pk
                or existing.request_id != request_id
                or existing.attempt_id != attempt_id
            ):
                raise AdmissionError("invalid_attempt", "Request and attempt IDs cannot be reused")
            if existing.status == AttemptStatus.PENDING and _eligible(room, user, check_window=False):
                _automatic_approval(room, existing)
            return existing
        admission, _ = SessionAdmission.objects.get_or_create(session=room.session, user=user)
        can_request = (
            _initial_join_window(room, user, admission)
            if settings.SERVER_ENFORCED_ADMISSION
            else room.session.can_join(user)
        )
        if not _eligible(room, user, check_window=False) or not can_request:
            raise AdmissionError("not_eligible", "User is not eligible to request admission")
        if user.slug != room.keeper and admission.state == AdmissionState.PERMANENTLY_DECLINED:
            raise AdmissionError("not_eligible", "Admission is permanently declined")
        _finish_attempts(
            admission.attempts.filter(status__in=ACTIVE_STATUSES), AttemptStatus.SUPERSEDED, schedule=False
        )
        try:
            # A savepoint also handles a UUID collision with another Session's writer.
            with transaction.atomic():
                attempt = AdmissionAttempt.objects.create(
                    admission=admission,
                    request_id=request_id,
                    attempt_id=attempt_id,
                    expires_at=max(timezone.now(), room.session.start) + timedelta(minutes=20),
                    returning=admission.state == AdmissionState.ADMITTED,
                )
        except IntegrityError as error:
            raise AdmissionError("invalid_attempt", "Request and attempt IDs cannot be reused") from error
        if not _automatic_approval(room, attempt):
            bump_admission_version(room.session_id, user.slug)
            _queue_permissions(admission)
        return attempt


def _attempt(room: Room, request_id: UUID, attempt_id: UUID) -> AdmissionAttempt:
    attempt = (
        AdmissionAttempt.objects.select_related("admission", "admission__user")
        .filter(admission__session=room.session, request_id=request_id, attempt_id=attempt_id)
        .first()
    )
    if not attempt:
        raise AdmissionError("invalid_attempt", "No matching admission attempt")
    return attempt


def decide_admission(
    session_slug: str,
    actor: User,
    request_id: UUID,
    attempt_id: UUID,
    decision: str,
    *,
    expected_version: int,
    expected_room_version: int,
) -> AdmissionAttempt:
    with _locked_room(session_slug) as room:
        _keeper(room, actor, expected_room_version)
        attempt = _attempt(room, request_id, attempt_id)
        _version(attempt.version, expected_version)
        if attempt.status != AttemptStatus.PENDING:
            raise AdmissionError("invalid_attempt", "Only a live pending attempt may be decided")
        if not _eligible(room, attempt.admission.user, check_window=False):
            raise AdmissionError("not_eligible", "User is no longer eligible")
        if attempt.admission.user.slug == room.keeper:
            raise AdmissionError("invalid_attempt", "The Keeper bypasses admission")
        match decision:
            case "approve":
                if attempt.admission.state == AdmissionState.PERMANENTLY_DECLINED:
                    raise AdmissionError("not_eligible", "Remove the permanent decline first")
                _approve(attempt, actor)
            case "decline":
                _set_attempt(attempt, AttemptStatus.DECLINED, actor)
            case "permanently_decline":
                _set_membership(attempt.admission, AdmissionState.PERMANENTLY_DECLINED, actor, schedule=False)
                _set_attempt(attempt, AttemptStatus.PERMANENTLY_DECLINED, actor)
            case _:
                raise AdmissionError("invalid_attempt", "Unknown admission decision")
        return attempt


def update_approval_required(
    session_slug: str,
    actor: User,
    approval_required: bool,
    *,
    expected_revision: int,
    expected_room_version: int,
) -> Room:
    with _locked_room(session_slug) as room:
        _keeper(room, actor, expected_room_version)
        _version(room.admission_revision, expected_revision)
        if room.approval_required != approval_required:
            room.approval_required = approval_required
            room.admission_revision += 1
            room.save(update_fields=["approval_required", "admission_revision", "date_modified"])
            bump_admission_version(room.session_id)
        if not approval_required:
            pending = (
                AdmissionAttempt.objects.select_related("admission", "admission__user")
                .filter(admission__session=room.session, status=AttemptStatus.PENDING)
                .order_by("date_created", "pk")
            )
            for attempt in pending:
                if attempt.admission.state != AdmissionState.PERMANENTLY_DECLINED and _eligible(
                    room, attempt.admission.user, check_window=False
                ):
                    _automatic_approval(room, attempt, actor)
        return room


def _change_membership(
    session_slug: str,
    actor: User,
    user: User,
    state: AdmissionState,
    expected_version: int,
    expected_room_version: int,
) -> SessionAdmission:
    with _locked_room(session_slug) as room:
        _keeper(room, actor, expected_room_version)
        if user.slug == room.keeper:
            raise AdmissionError("invalid_attempt", "The Keeper bypasses admission")
        admission, _ = SessionAdmission.objects.get_or_create(session=room.session, user=user)
        _version(admission.version, expected_version)
        if state == AdmissionState.NONE and admission.state != AdmissionState.PERMANENTLY_DECLINED:
            raise AdmissionError("invalid_attempt", "User is not permanently declined")
        # Revocation must not accidentally clear a permanent decline.
        target = (
            AdmissionState.PERMANENTLY_DECLINED
            if admission.state == AdmissionState.PERMANENTLY_DECLINED and state == AdmissionState.REVOKED
            else state
        )
        _set_membership(admission, target, actor)
        if state == AdmissionState.REVOKED:
            _finish_attempts(
                admission.attempts.filter(status__in=ACTIVE_STATUSES), AttemptStatus.REVOKED, schedule=False
            )
            if settings.SERVER_ENFORCED_ADMISSION:
                from ..state_machine import prune_participant

                prune_participant(room, user.slug, actor=actor.slug)
        return admission


def allow_previously_declined(
    session_slug: str, actor: User, user: User, *, expected_version: int, expected_room_version: int
) -> SessionAdmission:
    return _change_membership(session_slug, actor, user, AdmissionState.NONE, expected_version, expected_room_version)


def revoke_admission(
    session_slug: str, actor: User, user: User, *, expected_version: int, expected_room_version: int
) -> SessionAdmission:
    return _change_membership(
        session_slug, actor, user, AdmissionState.REVOKED, expected_version, expected_room_version
    )


def _participant_transition(
    session_slug: str,
    user: User,
    request_id: UUID,
    attempt_id: UUID,
    expected_version: int,
    status: AttemptStatus,
    permission_proof: tuple[int, str] | None = None,
) -> AdmissionAttempt:
    with _locked_room(session_slug) as room:
        _require_open(room)
        attempt = _attempt(room, request_id, attempt_id)
        if attempt.admission.user_id != user.pk or not user.is_active:
            raise AdmissionError("invalid_attempt", "Attempt belongs to another user")
        current = attempt.admission.attempts.order_by("-date_created", "-pk").first()
        if not current or current.pk != attempt.pk:
            raise AdmissionError("invalid_attempt", "A newer attempt superseded this receipt")
        if status == attempt.status and status in [AttemptStatus.ADMITTED, AttemptStatus.CANCELLED]:
            if status == AttemptStatus.ADMITTED and (
                not _eligible(room, user, check_window=False)
                or (user.slug != room.keeper and attempt.admission.state != AdmissionState.ADMITTED)
            ):
                raise AdmissionError("not_eligible", "Admission was revoked after activation")
            return attempt
        _version(attempt.version, expected_version)
        allowed = [AttemptStatus.GRANTING] if status == AttemptStatus.ADMITTED else ACTIVE_STATUSES
        if attempt.status not in allowed:
            raise AdmissionError("invalid_attempt", "Attempt is no longer active")
        if status == AttemptStatus.ADMITTED and (
            not _eligible(room, user, check_window=False)
            or (user.slug != room.keeper and attempt.admission.state != AdmissionState.ADMITTED)
        ):
            raise AdmissionError("not_eligible", "User is no longer authorized to complete admission")
        if status == AttemptStatus.ADMITTED and settings.SERVER_ENFORCED_ADMISSION:
            from ..state_machine import record_join
            from .capacity import ensure_admission_capacity
            from .permissions import permissions_reconciled

            ensure_admission_capacity(room, user)
            if (
                permission_proof is None
                or not permissions_reconciled(attempt.admission, permission_proof)
                or (attempt.participant_sid and attempt.participant_sid != permission_proof[1])
            ):
                raise AdmissionError("permission_pending", "LiveKit permissions have not been reconciled")
            # Internal callers may have no separate connection receipt. The
            # verified LiveKit proof, never a token request, supplies that SID.
            attempt.participant_sid = permission_proof[1]
            attempt.connected_at = attempt.connected_at or timezone.now()
            # Activation and attendance commit together, including the Keeper.
            _set_attempt(attempt, status)
            record_join(room.session, user)
        else:
            _set_attempt(attempt, status)
        return attempt


def cancel_admission(
    session_slug: str, user: User, request_id: UUID, attempt_id: UUID, *, expected_version: int
) -> AdmissionAttempt:
    return _participant_transition(
        session_slug, user, request_id, attempt_id, expected_version, AttemptStatus.CANCELLED
    )


def complete_admission(
    session_slug: str, user: User, request_id: UUID, attempt_id: UUID, *, expected_version: int
) -> AdmissionAttempt:
    proof = None
    if settings.SERVER_ENFORCED_ADMISSION:
        from ..livekit import LiveKitPermissionError
        from .permissions import verify_current_permissions

        attempt = AdmissionAttempt.objects.filter(
            admission__session__slug=session_slug,
            admission__user=user,
            request_id=request_id,
            attempt_id=attempt_id,
        ).first()
        if not attempt:
            raise AdmissionError("invalid_attempt", "No matching owned admission attempt")
        if attempt.status == AttemptStatus.ADMITTED:
            return _participant_transition(
                session_slug, user, request_id, attempt_id, expected_version, AttemptStatus.ADMITTED
            )
        _version(attempt.version, expected_version)
        try:
            proof = verify_current_permissions(attempt.admission_id)
        except LiveKitPermissionError as error:
            raise AdmissionError(
                "permission_pending", f"LiveKit completion verification failed: {error.code}"
            ) from error
    return _participant_transition(
        session_slug, user, request_id, attempt_id, expected_version, AttemptStatus.ADMITTED, proof
    )


def record_removal(
    session_slug: str, actor: User, user: User, *, expected_room_version: int, ban: bool = False
) -> None:
    """Commit revocation before ejection; uncertain transport outcomes fail closed."""
    with _locked_room(session_slug) as room:
        _keeper(room, actor, expected_room_version)
        if user.slug == room.keeper:
            raise AdmissionError("invalid_attempt", "Cannot remove the current Keeper")
        if (
            not room.session.attendees.filter(pk=user.pk).exists()
            and not room.session.admissions.filter(user=user).exists()
        ):
            raise AdmissionError("not_eligible", "Target does not belong to this Session")
        if ban and user.slug not in room.banned_participants:
            from functools import partial

            from ..livekit import publish_state
            from ..schemas import BanParticipantEvent
            from ..state_machine import apply_event

            state = apply_event(
                session_slug,
                actor.slug,
                BanParticipantEvent(participantSlug=user.slug),
                expected_room_version,
                connected=None,
            )
            transaction.on_commit(partial(publish_state, session_slug, state))
        else:
            revoke_removed_user(room.session, actor, user)


def revoke_removed_user(session: Session, actor: User, user: User, *, prune: bool = True) -> None:
    """Record explicit removal, not normal disconnect. Caller holds the Session lock."""
    member: SessionAdmission | None
    if settings.SERVER_ENFORCED_ADMISSION:
        member, _ = SessionAdmission.objects.get_or_create(session=session, user=user)
    else:
        member = SessionAdmission.objects.filter(session=session, user=user).first()
    if member:
        state = (
            AdmissionState.PERMANENTLY_DECLINED
            if member.state == AdmissionState.PERMANENTLY_DECLINED
            else AdmissionState.REVOKED
        )
        _set_membership(member, state, actor)
        _finish_attempts(member.attempts.filter(status__in=ACTIVE_STATUSES), AttemptStatus.REVOKED, schedule=False)
    if prune and settings.SERVER_ENFORCED_ADMISSION:
        from ..state_machine import prune_participant

        room = Room.objects.get(session=session)
        room.session = session
        prune_participant(room, user.slug, actor=actor.slug)


def get_admission(session_slug: str, user: User) -> SessionAdmission | None:
    with _locked_room(session_slug) as room:
        return SessionAdmission.objects.filter(session=room.session, user=user).first()


def pending_queue(session_slug: str, actor: User) -> list[AdmissionAttempt]:
    with _locked_room(session_slug) as room:
        if not actor.is_active or actor.slug != room.keeper:
            raise AdmissionError("not_keeper", "Only the current Keeper may read the queue")
        return list(
            AdmissionAttempt.objects.filter(admission__session=room.session, status=AttemptStatus.PENDING).order_by(
                "date_created", "pk"
            )
        )


def is_authorized_to_enter(session_slug: str, user: User) -> bool:
    with _locked_room(session_slug) as room:
        if (
            room.status == RoomStatus.ENDED
            or room.session.cancelled
            or room.session.ended()
            or not _eligible(room, user, check_window=not settings.SERVER_ENFORCED_ADMISSION)
        ):
            return False
        if user.slug == room.keeper:
            return True
        admission = SessionAdmission.objects.filter(session=room.session, user=user).first()
        if admission and admission.state == AdmissionState.PERMANENTLY_DECLINED:
            return False
        return admission is not None and admission.state == AdmissionState.ADMITTED


def _initial_join_window(room: Room, user: User, admission: SessionAdmission) -> bool:
    """Admission, not legacy token attendance, establishes returning privileges."""
    from totem.spaces.models import _default_grace_period

    now = timezone.now()
    returning = user.slug == room.keeper or admission.state == AdmissionState.ADMITTED
    wide = returning or user.is_staff
    opens = room.session.start - timedelta(minutes=60 if wide else 15)
    if returning:
        # _require_open enforces ended_at and the existing LiveKit overrun backstop.
        return opens < now and not room.session.ended()
    closes = room.session.end() if wide else room.session.start + _default_grace_period
    return opens < now < closes


def _join_candidate(room: Room, user: User, request_id: UUID, attempt_id: UUID) -> AdmissionAttempt:
    _require_open(room)
    if not _eligible(room, user, check_window=False):
        raise AdmissionError("not_eligible", "User is not an active, eligible attendee")
    attempt = _attempt(room, request_id, attempt_id)
    if attempt.admission.user_id != user.pk:
        raise AdmissionError("invalid_attempt", "This attempt belongs to another identity")
    member = attempt.admission
    if member.state == AdmissionState.PERMANENTLY_DECLINED and user.slug != room.keeper:
        raise AdmissionError("permanently_declined", "Admission is permanently declined")
    latest = member.attempts.order_by("-date_created", "-pk").first()
    if not latest or latest.pk != attempt.pk:
        raise AdmissionError("invalid_attempt", "A newer connection attempt superseded this request")
    if attempt.status not in [AttemptStatus.PENDING, AttemptStatus.GRANTING, AttemptStatus.ADMITTED]:
        raise AdmissionError("invalid_attempt", "This admission attempt is no longer valid")
    if attempt.status in ACTIVE_STATUSES and attempt.expires_at <= timezone.now():
        raise AdmissionError("invalid_attempt", "Admission attempt expired")
    if attempt.status == AttemptStatus.ADMITTED and not _initial_join_window(room, user, member):
        raise AdmissionError("not_eligible", "Session is not joinable at this time")
    return attempt


def prepare_admission_join(
    session_slug: str,
    user: User,
    *,
    request_id: UUID | None = None,
    attempt_id: UUID | None = None,
    connected: set[str] | None = None,
) -> JoinResponse:
    """Persist the request before trying to reserve/sign a connection token.

    Full transport capacity never silently discards the pending application.
    The API supplies raw presence observed outside transactions. Token leases
    serialize concurrent issuance even before those connections reach LiveKit.
    """
    from ..livekit import create_access_token
    from ..models import AdmissionPermissionSync
    from ..schemas import AdmissionJoinState, JoinResponse
    from .capacity import has_admission_capacity, reserve_connection

    if connected is None:
        raise AdmissionError("presence_unavailable", "Raw LiveKit presence is required to reserve a connection")
    with _locked_room(session_slug) as room:
        _require_open(room)
        if not _eligible(room, user, check_window=False):
            raise AdmissionError("not_eligible", "User is not an active, eligible attendee")
        member, _ = SessionAdmission.objects.get_or_create(session=room.session, user=user)
        if member.state == AdmissionState.PERMANENTLY_DECLINED and user.slug != room.keeper:
            raise AdmissionError("permanently_declined", "Admission is permanently declined")
        latest = member.attempts.order_by("-date_created", "-pk").first()
        if request_id is not None or attempt_id is not None:
            if request_id is None or attempt_id is None:
                raise AdmissionError("invalid_attempt", "Both request and attempt UUIDs are required")
            attempt = request_admission(session_slug, user, request_id, attempt_id)
        elif latest and latest.status in ACTIVE_STATUSES:
            attempt = request_admission(session_slug, user, latest.request_id, latest.attempt_id)
        elif (
            latest
            and latest.status != AttemptStatus.ADMITTED
            and member.state != AdmissionState.ADMITTED
            and user.slug != room.keeper
        ):
            raise AdmissionError("invalid_attempt", "A terminal attempt requires an explicit new admission request")
        else:
            attempt = request_admission(session_slug, user, uuid4(), uuid4())
        _join_candidate(room, user, attempt.request_id, attempt.attempt_id)
        request_id, attempt_id = attempt.request_id, attempt.attempt_id

    with _locked_room(session_slug) as room:
        attempt = _join_candidate(room, user, request_id, attempt_id)
        member = attempt.admission
        admitted = user.slug == room.keeper or (
            member.state == AdmissionState.ADMITTED
            and attempt.status in [AttemptStatus.GRANTING, AttemptStatus.ADMITTED]
            and has_admission_capacity(room, user)
        )
        reserve_connection(room, user, attempt, connected, admitted=admitted)
        token = create_access_token(
            user,
            session_slug,
            admitted=admitted,
            attributes={
                "totem.admission": "admitted" if admitted else "waiting",
                "totem.admission_attempt": str(attempt.attempt_id),
            },
        )
        sync = AdmissionPermissionSync.objects.filter(admission=member).first()
        permission_state = "pending"
        if sync:
            permission_state = sync.last_error or ("applied" if sync.applied_revision == sync.revision else "pending")
        block_reason = None
        if not admitted and member.state == AdmissionState.REVOKED:
            block_reason = "requires_reapproval"
        elif not admitted and not has_admission_capacity(room, user):
            block_reason = "admission_full"
        return JoinResponse(
            token=token,
            is_already_present=user.slug in connected,
            admission=AdmissionJoinState(
                request_id=attempt.request_id,
                attempt_id=attempt.attempt_id,
                status=attempt.status,
                durable_state=member.state,
                approval_required=room.approval_required,
                expires_at=attempt.expires_at,
                permissions="admitted" if admitted else "waiting",
                permission_sync=permission_state,
                revision=sync.revision if sync else 0,
                admission_block_reason=block_reason,
            ),
        )
