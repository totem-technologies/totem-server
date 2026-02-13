import logging
from datetime import timedelta

from django.utils import timezone

from totem.meetings.livekit_provider import RoomAlreadyEndedError, RoomNotFoundError, end_room, is_user_in_room
from totem.spaces.models import Session


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
        keeper = session.space.author
        keeper_in_joined = keeper in session.joined.all()

        if keeper_in_joined:
            continue

        keeper_in_livekit = is_user_in_room(room_name=session.slug, user_identity=keeper.slug)
        if keeper_in_livekit:
            continue

        session.ended_at = timezone.now()
        session.save()
        ended_count += 1
        logging.warning(f"Ended session {session.slug} - keeper {keeper.email} did not join")

        try:
            end_room(session.slug)
        except (RoomNotFoundError, RoomAlreadyEndedError):
            pass

    return ended_count


tasks = [end_sessions_without_keeper]
