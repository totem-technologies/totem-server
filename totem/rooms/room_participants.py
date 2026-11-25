"""Admission-backed projection of room membership and LiveKit presence.

Callers that mutate room state must hold the session lock.
"""

from dataclasses import dataclass

from .admission.capacity import admission_limit, admission_slots_used
from .models import AdmissionAttempt, AdmissionState, AttemptStatus, Room
from .schemas import RoomStatus


@dataclass
class ParticipantProjection:
    retained: set[str]
    connected: set[str]


def participant_projection(
    room: Room, raw_connected: set[str], observed_sids: dict[str, str] | None = None
) -> ParticipantProjection:
    retained: set[str] = set()
    connected: set[str] = set()
    attendees = set(room.session.attendees.filter(is_active=True).values_list("slug", flat=True))
    over_capacity = admission_slots_used(room) > admission_limit(room)
    admissions = room.session.admissions.select_related("user", "permission_sync").prefetch_related("attempts")
    for admission in admissions:
        slug = admission.user.slug
        keeper = slug == room.keeper
        if slug in room.banned_participants:
            continue
        if slug not in attendees or (not keeper and admission.state != AdmissionState.ADMITTED):
            continue
        attempts = sorted(
            admission.attempts.all(), key=lambda attempt: (attempt.date_created, attempt.pk), reverse=True
        )
        if not any(attempt.status == AttemptStatus.ADMITTED for attempt in attempts):
            continue
        retained.add(slug)
        if (over_capacity and not keeper) or attempts[0].status != AttemptStatus.ADMITTED:
            continue
        sync = getattr(admission, "permission_sync", None)
        if (
            slug in raw_connected
            and sync is not None
            and attempts[0].participant_sid
            and attempts[0].participant_sid == sync.participant_sid
            and observed_sids is not None
            and observed_sids.get(slug) == attempts[0].participant_sid
            and sync.desired_admitted
            and sync.applied_revision == sync.revision
            and not sync.last_error
            and sync.operation_id is None
        ):
            connected.add(slug)
    if room.status == RoomStatus.ENDED or room.session.cancelled or room.session.ended():
        connected.clear()
    return ParticipantProjection(retained=retained, connected=connected)


def is_activated_participant(room: Room, user_slug: str) -> bool:
    """Check the persisted activation checkpoint, not current LiveKit presence.

    Only use this under the Session lock after the caller has verified a fresh
    permission receipt. Live presence requires participant_projection with an
    independently observed SID snapshot.
    """
    attempt = (
        AdmissionAttempt.objects.filter(admission__session_id=room.session_id, admission__user__slug=user_slug)
        .order_by("-date_created", "-pk")
        .first()
    )
    observed_sids = {user_slug: attempt.participant_sid} if attempt else {}
    return user_slug in participant_projection(room, {user_slug}, observed_sids).connected
