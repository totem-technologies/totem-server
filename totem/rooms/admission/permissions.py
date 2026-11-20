"""Durable, retryable reconciliation of Django admission with LiveKit permissions."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from functools import partial
from uuid import UUID, uuid4

from django.db import connection, transaction
from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone

from totem.spaces.models import LIVEKIT_ENDED_BACKSTOP, SESSION_END_TIME, Session

from ..livekit import (
    LiveKitPermissionError,
    get_participant_snapshot,
    hard_disconnect_participant,
    update_participant_permissions,
)
from ..models import AdmissionPermissionSync, AdmissionState, AttemptStatus, Room, SessionAdmission
from ..schemas import RoomStatus
from .notifications import bump_admission_version

logger = logging.getLogger(__name__)
PERMISSION_LEASE_SECONDS = 30


def desired_permissions(room: Room, admission: SessionAdmission) -> bool:
    """Caller holds the Session lock. Metadata is never authorization input."""
    if (
        room.status == RoomStatus.ENDED
        or room.session.cancelled
        or room.session.ended()
        or not admission.user.is_active
        or admission.user.slug in room.banned_participants
        or not room.session.attendees.filter(pk=admission.user_id).exists()
    ):
        return False
    if admission.user.slug == room.keeper:
        return True
    if admission.state != AdmissionState.ADMITTED:
        return False
    from .capacity import has_admission_capacity

    if not has_admission_capacity(room, admission.user):
        return False
    attempt = admission.attempts.order_by("-date_created", "-pk").first()
    return attempt is None or (
        attempt.status in [AttemptStatus.GRANTING, AttemptStatus.ADMITTED]
        and (attempt.status == AttemptStatus.ADMITTED or attempt.expires_at > timezone.now())
    )


def _requires_disconnect(room: Room, admission: SessionAdmission) -> bool:
    attempt = admission.attempts.order_by("-date_created", "-pk").first()
    return bool(
        room.status == RoomStatus.ENDED
        or room.session.cancelled
        or room.session.ended()
        or admission.state == AdmissionState.PERMANENTLY_DECLINED
        or (admission.state == AdmissionState.REVOKED and (not attempt or attempt.status != AttemptStatus.PENDING))
        or admission.user.slug in room.banned_participants
        or not admission.user.is_active
        or not room.session.attendees.filter(pk=admission.user_id).exists()
        or (
            attempt
            and (
                attempt.status not in [AttemptStatus.PENDING, AttemptStatus.GRANTING, AttemptStatus.ADMITTED]
                or (
                    attempt.status in [AttemptStatus.PENDING, AttemptStatus.GRANTING]
                    and attempt.expires_at <= timezone.now()
                )
            )
        )
    )


def queue_permission_sync(admission: SessionAdmission) -> None:
    """Caller holds the Session lock. Persist intent before scheduling I/O."""
    room = Room.objects.select_related("session").get(session_id=admission.session_id)
    # Reload: callers may have changed another instance of the same membership.
    admission = SessionAdmission.objects.select_related("user").get(pk=admission.pk)
    sync, _ = AdmissionPermissionSync.objects.get_or_create(admission=admission)
    sync.revision += 1
    sync.desired_admitted = desired_permissions(room, admission)
    sync.authority_keeper = room.keeper
    sync.last_error = ""
    sync.retry_count = 0
    sync.next_retry_at = None
    sync.save()
    transaction.on_commit(partial(reconcile_admission_permissions, admission.pk))


@contextmanager
def _locked_sync(admission_id: int) -> Iterator[tuple[Room, SessionAdmission, AdmissionPermissionSync]]:
    session_id = SessionAdmission.objects.values_list("session_id", flat=True).get(pk=admission_id)
    with transaction.atomic():
        session = Session.objects.select_for_update().get(pk=session_id)
        room = Room.objects.get(session=session)
        room.session = session
        admission = SessionAdmission.objects.select_related("user").get(pk=admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=admission)
        before = _visible_state(sync)
        yield room, admission, sync
        if _visible_state(sync) != before:
            bump_admission_version(session.pk, admission.user.slug)


def _visible_state(sync: AdmissionPermissionSync) -> tuple:
    return (
        sync.revision,
        sync.desired_admitted,
        sync.authority_keeper,
        sync.applied_revision,
        sync.participant_sid,
        sync.last_error,
        sync.next_retry_at,
    )


def _retry_later(sync: AdmissionPermissionSync) -> None:
    sync.retry_count += 1
    sync.next_retry_at = timezone.now() + timedelta(seconds=min(2 ** min(sync.retry_count, 6), 60))


def _refresh_intent(room: Room, admission: SessionAdmission, sync: AdmissionPermissionSync) -> None:
    desired = desired_permissions(room, admission)
    if desired != sync.desired_admitted or sync.authority_keeper != room.keeper:
        sync.revision += 1
        sync.desired_admitted = desired
        sync.authority_keeper = room.keeper
        sync.applied_revision = None
        sync.retry_count = 0
        sync.next_retry_at = None
        sync.save()


def _current(admission_id: int, operation_id: UUID, revision: int) -> bool:
    with _locked_sync(admission_id) as (room, admission, sync):
        _refresh_intent(room, admission, sync)
        return sync.operation_id == operation_id and sync.revision == revision


def _restrict(room_name: str, identity: str) -> str:
    """Compensate an uncertain/stale grant. Failure stays durable for retry."""
    try:
        update_participant_permissions(room_name, identity, admitted=False)
        return ""
    except LiveKitPermissionError as error:
        if error.code in ["participant_missing", "room_missing"]:
            return ""
        try:
            hard_disconnect_participant(room_name, identity)
            return ""
        except LiveKitPermissionError:
            return error.code


def reconcile_admission_permissions(admission_id: int, *, force: bool = False) -> None:
    """Serialize identity mutations with an expiring lease, not a DB transaction.

    A checked operation marks only its captured revision applied. Stale or
    uncertain grants are restricted again and left dirty; the periodic task
    retries even after process failure. LiveKit has no atomic SID precondition.
    """
    if connection.in_atomic_block:
        raise RuntimeError("LiveKit reconciliation must run outside database transactions")
    try:
        _reconcile(admission_id, force=force)
    except (SessionAdmission.DoesNotExist, AdmissionPermissionSync.DoesNotExist, Room.DoesNotExist):
        return
    except Exception:
        # Do not turn a committed admission command into a false HTTP failure.
        # The lease expires and the persisted intent remains retryable.
        logger.exception("Admission permission reconciliation failed for %s", admission_id)


def _reconcile(admission_id: int, *, force: bool = False) -> None:
    operation_id = uuid4()
    with _locked_sync(admission_id) as (room, admission, sync):
        _refresh_intent(room, admission, sync)
        if sync.lease_until and sync.lease_until > timezone.now():
            return
        if not force and sync.next_retry_at and sync.next_retry_at > timezone.now():
            return
        recovered_lease = sync.operation_id is not None
        sync.operation_id = operation_id
        sync.lease_until = timezone.now() + timedelta(seconds=PERMISSION_LEASE_SECONDS)
        sync.save()
        revision = sync.revision
        desired = sync.desired_admitted
        attempt = admission.attempts.order_by("-date_created", "-pk").first()
        activated_sid = attempt.participant_sid if attempt and attempt.status == AttemptStatus.ADMITTED else None
        disconnect = not desired and _requires_disconnect(room, admission)
        room_name, identity = room.session.slug, admission.user.slug

    error_code = ""
    participant_sid = ""

    try:
        if recovered_lease:
            restriction_error = _restrict(room_name, identity)
            if restriction_error:
                raise LiveKitPermissionError(restriction_error, "Could not recover an uncertain operation")
            # A recovered lease may have belonged to a paused grant worker.
            # Leave this pass restricted; a separate observation may grant later.
            raise LiveKitPermissionError("lease_recovered", "Recovered uncertain permission operation")
        participant = get_participant_snapshot(room_name, identity)
        if desired and activated_sid is not None and participant.sid != activated_sid:
            raise LiveKitPermissionError("identity_replaced", "Activated connection changed; request a new attempt")
        if not _current(admission_id, operation_id, revision):
            raise LiveKitPermissionError("stale_operation", "Admission changed before permission update")
        after = update_participant_permissions(
            room_name,
            identity,
            admitted=desired,
            expected_sid=participant.sid,
            attributes={
                "totem.admission": "admitted" if desired else "waiting",
                "totem.admission_revision": str(revision),
            },
        )
        participant_sid = after.sid
        if disconnect:
            if not _current(admission_id, operation_id, revision):
                raise LiveKitPermissionError("stale_operation", "Admission changed before disconnect")
            hard_disconnect_participant(room_name, identity)
    except LiveKitPermissionError as error:
        error_code = error.code

    with _locked_sync(admission_id) as (room, admission, sync):
        _refresh_intent(room, admission, sync)
        owns_lease = sync.operation_id == operation_id
        current = owns_lease and sync.revision == revision
        absent_denial = not desired and error_code in ["participant_missing", "room_missing"]
        if current and (not error_code or absent_denial):
            sync.operation_id = None
            sync.lease_until = None
            sync.checked_at = timezone.now()
            sync.last_error = ""
            sync.applied_revision = revision
            sync.participant_sid = participant_sid
            sync.retry_count = 0
            sync.next_retry_at = None
            sync.save()
            return
        # Keep our lease during compensation, including a change after the last
        # post-update check. A newer worker cannot grant over this restriction.
        if owns_lease:
            sync.applied_revision = None
            sync.last_error = error_code or "stale_operation"
            sync.save()

    restriction_error = ""
    if error_code != "lease_recovered" and (not current or error_code not in ["participant_missing", "room_missing"]):
        restriction_error = _restrict(room_name, identity)
    with _locked_sync(admission_id) as (_room, _admission, sync):
        if sync.operation_id == operation_id:
            sync.operation_id = None
            sync.lease_until = None
            sync.checked_at = timezone.now()
            sync.last_error = restriction_error or error_code or "stale_operation"
            sync.applied_revision = None
            _retry_later(sync)
            sync.save()
        else:
            # Compensation may have restricted a replacement worker's connection.
            # Fence its acknowledgement too, without stealing its active lease.
            sync.revision += 1
            sync.applied_revision = None
            sync.last_error = restriction_error or "stale_operation"
            _retry_later(sync)
            sync.save()


def verify_current_permissions(admission_id: int) -> tuple[int, str]:
    """Observe the current connection outside a transaction before readiness commit."""
    if connection.in_atomic_block:
        raise LiveKitPermissionError("permission_pending", "Completion must be verified outside a transaction")
    sync = (
        AdmissionPermissionSync.objects.select_related("admission__session", "admission__user")
        .filter(admission_id=admission_id)
        .first()
    )
    if sync and not permissions_reconciled(sync.admission):
        # The token was delivered after the initial on-commit lookup. Readiness
        # is a connection-observed retry, not dependent on the background cadence.
        reconcile_admission_permissions(admission_id)
        sync.refresh_from_db()
    if not sync or not permissions_reconciled(sync.admission):
        raise LiveKitPermissionError("permission_pending", "No reconciled permission operation")
    try:
        participant = get_participant_snapshot(sync.admission.session.slug, sync.admission.user.slug)
        if participant.sid != sync.participant_sid:
            raise LiveKitPermissionError("identity_replaced", "Connection changed before completion")
        permission = participant.permission
        if not (
            permission.can_publish
            and permission.can_subscribe
            and permission.can_publish_data
            and not permission.can_update_metadata
            and not permission.hidden
        ):
            raise LiveKitPermissionError("permission_mismatch", "Current connection is not admitted")
    except LiveKitPermissionError as error:
        with _locked_sync(admission_id) as (_room, _admission, current):
            if current.revision == sync.revision and current.participant_sid == sync.participant_sid:
                current.applied_revision = None
                current.last_error = error.code
                _retry_later(current)
                current.save()
        raise
    return sync.revision, sync.participant_sid


def permissions_reconciled(admission: SessionAdmission, proof: tuple[int, str] | None = None) -> bool:
    sync = AdmissionPermissionSync.objects.filter(admission=admission).first()
    return bool(
        sync
        and sync.desired_admitted
        and sync.applied_revision == sync.revision
        and sync.participant_sid
        and not sync.last_error
        and sync.operation_id is None
        and (proof is None or proof == (sync.revision, sync.participant_sid))
    )


def reconcile_session_permissions() -> int:
    """Recheck clean live-session rows for token replay.

    Require a post-token-TTL observation before retiring clean ended Sessions.
    Unresolved restrictions are retried regardless of Session age.
    Live sessions are checked even after an acknowledged denial, since self-hosted
    deployments need reconciliation for replayed unexpired tokens.
    """
    # For implicit endings, the backstop is a conservative upper bound even
    # when the room did not qualify for an overrun.
    implicit_end = (
        Session.objects.filter(pk=OuterRef("admission__session_id"))
        .annotate(end_bound=SESSION_END_TIME + LIVEKIT_ENDED_BACKSTOP)
        .values("end_bound")
    )
    admissions = AdmissionPermissionSync.objects.filter(
        Q(admission__session__in=Session.objects.not_ended())
        | Q(admission__session__ended_at__gte=timezone.now() - timedelta(minutes=2))
        | Q(admission__session__ended_at__isnull=True, checked_at__lt=Subquery(implicit_end) + timedelta(minutes=2))
        | Q(desired_admitted=True)
        | Q(checked_at__isnull=True)
        | Q(checked_at__lt=F("admission__session__ended_at") + timedelta(minutes=2))
        | Q(applied_revision__isnull=True)
        | ~Q(applied_revision=F("revision"))
    ).values_list("admission_id", flat=True)
    count = 0
    for admission_id in admissions.iterator():
        reconcile_admission_permissions(admission_id)
        count += 1
    return count
