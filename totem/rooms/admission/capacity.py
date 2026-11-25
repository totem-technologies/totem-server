"""Separate durable admission seats from short-lived LiveKit connection slots.

All decisions/reservations are made while holding the Session row lock. Raw
presence is an observation made outside that transaction, never authorization.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from totem.users.models import User

from ..livekit import ACCESS_TOKEN_TTL_SECONDS, ENFORCED_MAX_PARTICIPANTS, MAX_PARTICIPANTS, WAITING_CONNECTION_LIMIT
from ..models import AdmissionAttempt, AdmissionState, Room, SessionAdmission
from .schemas import AdmissionError


def admission_limit(room: Room) -> int:
    """Session seats include one reserved Keeper seat; staff RSVP is not a bypass."""
    return min(max(room.session.seats, 1), MAX_PARTICIPANTS)


def admission_slots_used(room: Room) -> int:
    return (
        1
        + SessionAdmission.objects.filter(session_id=room.session_id, state=AdmissionState.ADMITTED)
        .exclude(user__slug=room.keeper)
        .count()
    )


def has_admission_capacity(room: Room, user: User) -> bool:
    if user.slug == room.keeper:
        return True
    returning = SessionAdmission.objects.filter(
        session_id=room.session_id, user=user, state=AdmissionState.ADMITTED
    ).exists()
    used = admission_slots_used(room)
    return used <= admission_limit(room) if returning else used < admission_limit(room)


def ensure_admission_capacity(room: Room, user: User) -> None:
    if not has_admission_capacity(room, user):
        raise AdmissionError("admission_full", "This Session has no unreserved admission seats")


def connection_reservations(room: Room, raw_connected: set[str]) -> tuple[set[str], set[str]]:
    """Return occupied identities and waiting reservations, not attendance."""
    leases = set(
        AdmissionAttempt.objects.filter(
            admission__session_id=room.session_id, token_expires_at__gt=timezone.now()
        ).values_list("admission__user__slug", flat=True)
    )
    occupied = raw_connected | leases
    authorised = {room.keeper}
    if admission_slots_used(room) <= admission_limit(room):
        authorised.update(
            SessionAdmission.objects.filter(session_id=room.session_id, state=AdmissionState.ADMITTED).values_list(
                "user__slug", flat=True
            )
        )
    return occupied, occupied - authorised


def reserve_connection(
    room: Room, user: User, attempt: AdmissionAttempt, raw_connected: set[str], *, admitted: bool
) -> None:
    """Reserve the JWT lifetime, including cancelled attempts whose JWTs still work.

    Missing-room presence is empty; failed lookup must never be invented as empty.
    A duplicate identity refresh consumes no additional physical connection slot.
    """
    occupied, waiting = connection_reservations(room, raw_connected)
    if not admitted and user.slug not in waiting and len(waiting) >= WAITING_CONNECTION_LIMIT:
        raise AdmissionError("waiting_full", "Restricted waiting connections are full; your request remains queued")
    if user.slug not in occupied and len(occupied | {user.slug, room.keeper}) > ENFORCED_MAX_PARTICIPANTS:
        raise AdmissionError("room_full", "LiveKit connection capacity is full; your request remains queued")
    attempt.token_expires_at = timezone.now() + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)
    attempt.save(update_fields=["token_expires_at", "date_modified"])
