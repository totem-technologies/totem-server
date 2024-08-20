from datetime import timedelta

from django.utils import timezone

from .models import CircleEvent


def notify_circle_ready():
    upcoming_circles = CircleEvent.objects.filter(
        start__gte=timezone.now(),
        start__lte=timezone.now() + timedelta(minutes=20),
        notified=False,
        cancelled=False,
    )
    for event in upcoming_circles:
        event.notify()


def notify_circle_tomorrow():
    upcoming_circles = CircleEvent.objects.filter(
        start__gte=timezone.now() + timedelta(hours=20),
        start__lte=timezone.now() + timedelta(days=1),
        notified_tomorrow=False,
        cancelled=False,
    )
    for event in upcoming_circles:
        event.notify_tomorrow()


def advertise_circle():
    upcoming_circles = CircleEvent.objects.filter(
        start__gte=timezone.now() + timedelta(days=2),
        start__lte=timezone.now() + timedelta(days=5),
        advertised=False,
        cancelled=False,
    )
    for event in upcoming_circles:
        event.advertise()


def notify_missed_event():
    recently_ended_events = CircleEvent.objects.filter(
        start__gte=timezone.now() - timedelta(hours=2),
        start__lte=timezone.now() - timedelta(hours=1),
        cancelled=False,
        notified_missed=False,
    )
    print(f"Notifying {len(recently_ended_events)} missed events")
    for event in recently_ended_events:
        event.notify_missed()
    return len(recently_ended_events)


tasks = [notify_circle_ready, advertise_circle, notify_circle_tomorrow, notify_missed_event]
