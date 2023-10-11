from datetime import timedelta

from django.utils import timezone

from .models import CircleEvent


def notify_circle_ready():
    upcoming_circles = CircleEvent.objects.filter(
        start__gte=timezone.now(),
        start__lte=timezone.now() + timedelta(minutes=60),
        notified=False,
    )
    for event in upcoming_circles:
        event.notify()


def advertise_circle():
    upcoming_circles = CircleEvent.objects.filter(
        start__gte=timezone.now(),
        start__lte=timezone.now() + timedelta(days=7),
        advertised=False,
    )
    for event in upcoming_circles:
        event.advertise()


tasks = [notify_circle_ready, advertise_circle]
