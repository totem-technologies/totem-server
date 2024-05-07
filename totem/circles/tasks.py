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


tasks = [notify_circle_ready, advertise_circle, notify_circle_tomorrow]
