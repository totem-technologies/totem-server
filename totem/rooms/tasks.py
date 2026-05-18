import logging
from datetime import timedelta

from django.utils import timezone

from totem.rooms.livekit import get_connected_participants, publish_state
from totem.rooms.models import Room
from totem.rooms.schemas import EndReason, EndRoomEvent, RoomStatus
from totem.rooms.state_machine import apply_event
from totem.spaces.models import Session
from totem.users.models import User


def _end_session(session: Session, keeper: User, connected_participants: set[str]):
    session.ended_at = timezone.now()
    session.save(update_fields=["ended_at"])

    room = Room.objects.for_session(session.slug).first()
    if room and room.status != RoomStatus.ENDED:
        try:
            if len(connected_participants) > 0:
                reason = EndReason.KEEPER_ABSENT
            else:
                reason = EndReason.ROOM_EMPTY

            state = apply_event(
                session_slug=session.slug,
                actor=keeper.slug,
                event=EndRoomEvent(reason=reason),
                last_seen_version=room.state_version,
                connected=set(),
            )
        except Exception:
            logging.exception("Failed to end room for session %s", session.slug)
        else:
            try:
                publish_state(session.slug, state)
            except Exception:
                logging.exception("Failed to publish room state for session %s", session.slug)

    logging.warning(f"Ended session {session.slug}")


def end_sessions_without_keeper() -> int:
    """End sessions where the keeper has not joined within 5 minutes of the session start.

    Checks both the database joined list and LiveKit room presence for reliability.
    """
    grace_period = timedelta(minutes=5)
    sessions_to_check = Session.objects.filter(
        start__lte=timezone.now() - grace_period,
        start__gte=timezone.now() - timedelta(hours=1),  # recent sessions
        ended_at__isnull=True,
        cancelled=False,
    )
    ended_count = 0
    for session in sessions_to_check:
        keeper: User = session.space.author

        connected_participants = get_connected_participants(session.slug)
        keeper_in_livekit = keeper.slug in connected_participants
        if keeper_in_livekit:
            continue

        _end_session(session, keeper, connected_participants)
        ended_count += 1

    return ended_count


tasks = [end_sessions_without_keeper]
