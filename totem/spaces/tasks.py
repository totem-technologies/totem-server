from datetime import timedelta

from django.utils import timezone

from .models import LIVEKIT_ENDED_BACKSTOP, SESSION_END_TIME, Session


def notify_session_ready():
    upcoming_sessions = Session.objects.filter(
        start__gte=timezone.now(),
        start__lte=timezone.now() + timedelta(minutes=20),
        notified=False,
        cancelled=False,
    )
    for session in upcoming_sessions:
        session.notify()


def notify_session_tomorrow():
    upcoming_sessions = Session.objects.filter(
        start__gte=timezone.now() + timedelta(hours=20),
        start__lte=timezone.now() + timedelta(days=1),
        notified_tomorrow=False,
        cancelled=False,
    )
    for session in upcoming_sessions:
        session.notify_tomorrow()


def advertise_session():
    upcoming_sessions = Session.objects.filter(
        start__gte=timezone.now() + timedelta(days=2),
        start__lte=timezone.now() + timedelta(days=5),
        advertised=False,
        cancelled=False,
    )
    for session in upcoming_sessions:
        session.advertise()


def notify_missed_session():
    now = timezone.now()
    # LiveKit sessions can overrun their scheduled end by up to the backstop,
    # so look back far enough to catch them once they actually end.
    recently_ended_sessions = (
        Session.objects.alias(end_time=SESSION_END_TIME)
        .filter(
            end_time__gte=now - timedelta(hours=1) - LIVEKIT_ENDED_BACKSTOP,
            cancelled=False,
            notified_missed=False,
        )
        .ended()
    )
    print(f"Notifying {len(recently_ended_sessions)} missed sessions")
    for session in recently_ended_sessions:
        session.notify_missed()
    return len(recently_ended_sessions)


tasks = [notify_session_ready, advertise_session, notify_session_tomorrow, notify_missed_session]

notify_circle_ready = notify_session_ready
notify_circle_tomorrow = notify_session_tomorrow
advertise_circle = advertise_session
notify_missed_event = notify_missed_session
