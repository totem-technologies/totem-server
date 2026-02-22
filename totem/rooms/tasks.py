import logging
from datetime import timedelta

from django.utils import timezone

from totem.rooms.livekit import get_connected_participants, publish_state
from totem.rooms.models import Room
from totem.rooms.schemas import EndReason, EndRoomEvent, RoomStatus
from totem.rooms.state_machine import apply_event
from totem.spaces.models import Session
from totem.users.models import User


def end_sessions_without_keeper():
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
        keeper_in_joined = keeper in session.joined.all()

        if keeper_in_joined:
            continue

        keeper_in_livekit = keeper.slug in get_connected_participants(session.slug)
        if keeper_in_livekit:
            continue

        session.ended_at = timezone.now()
        session.save()
        ended_count += 1
        logging.warning(f"Ended session {session.slug} - keeper {keeper.email} did not join")

        room = Room.objects.for_session(session.slug).first()
        if room and room.status != RoomStatus.ENDED:
            try:
                state = apply_event(
                    session_slug=session.slug,
                    actor=keeper.slug,
                    event=EndRoomEvent(reason=EndReason.KEEPER_ABSENT),
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

    return ended_count


tasks = [end_sessions_without_keeper]
