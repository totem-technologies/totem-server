import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from totem.rooms.admission.permissions import reconcile_session_permissions
from totem.rooms.livekit import get_admission_participants, publish_state
from totem.rooms.models import Room
from totem.rooms.schemas import EndReason, EndRoomEvent, RoomStatus
from totem.rooms.state_machine import apply_event
from totem.spaces.models import Session


def _end_session(session: Session, connected_participants: set[str]) -> bool:
    from .admission import invalidate_pending_admission

    state = None
    with transaction.atomic():
        session = Session.objects.select_for_update().get(pk=session.pk)
        room = Room.objects.for_session(session.slug).first()
        keeper_slug = room.keeper if room else session.space.author.slug
        # Reassignment may have happened while presence was being fetched.
        already_ended = session.ended_at is not None
        if not already_ended and keeper_slug in connected_participants:
            return False
        if already_ended and (room is None or room.status == RoomStatus.ENDED):
            return False
        if not already_ended:
            session.ended_at = timezone.now()
            session.save(update_fields=["ended_at"])
        invalidate_pending_admission(session)
        if room and room.status != RoomStatus.ENDED:
            if already_ended:
                reason = EndReason(room.end_reason) if room.end_reason else EndReason.KEEPER_ENDED
            elif connected_participants:
                reason = EndReason.KEEPER_ABSENT
            else:
                reason = EndReason.ROOM_EMPTY
            try:
                with transaction.atomic():
                    state = apply_event(
                        session_slug=session.slug,
                        actor=room.keeper,
                        event=EndRoomEvent(reason=reason),
                        last_seen_version=room.state_version,
                        connected=None,
                    )
            except Exception:
                logging.exception("Failed to end room for session %s", session.slug)
    if state is not None:
        try:
            publish_state(session.slug, state)
        except Exception:
            logging.exception("Failed to publish room state for session %s", session.slug)
    logging.warning("Ended session %s", session.slug)
    return not already_ended


def end_sessions_without_keeper() -> int:
    """End sessions where the keeper has not joined within 5 minutes of the session start.

    Uses LiveKit presence when available, but skips sessions if participant
    lookup fails so a LiveKit outage cannot terminate active rooms.
    """
    grace_period = timedelta(minutes=5)
    sessions_to_check = Session.objects.filter(
        Q(
            start__lte=timezone.now() - grace_period,
            start__gte=timezone.now() - timedelta(hours=1),
            ended_at__isnull=True,
            cancelled=False,
        )
        | (Q(ended_at__isnull=False, room__isnull=False) & ~Q(room__status=RoomStatus.ENDED))
    )
    ended_count = 0
    for session in sessions_to_check:
        # A prior partial end stays closed for admission and retries canonical
        # room-state cleanup without requiring another presence observation.
        if session.ended_at is not None:
            _end_session(session, set())
            continue
        room = Room.objects.filter(session=session).first()
        keeper_slug = room.keeper if room else session.space.author.slug

        try:
            connected_participants = get_admission_participants(session.slug)
        except Exception:
            logging.exception("Skipped session %s because LiveKit presence failed", session.slug)
            continue
        if connected_participants is None:
            logging.warning("Skipped session %s because LiveKit participants could not be fetched", session.slug)
            continue

        keeper_in_livekit = keeper_slug in connected_participants
        if keeper_in_livekit:
            continue

        ended_count += int(_end_session(session, connected_participants))

    return ended_count


tasks = [end_sessions_without_keeper, reconcile_session_permissions]
