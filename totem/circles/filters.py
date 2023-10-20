from django.utils import timezone

from totem.users.models import User

from .models import CircleEvent


def upcoming_events_user_can_attend(user: User):
    events = CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, open=True)
    events = events.exclude(attendees=user)
    events = events.exclude(joined=user)
    events = events.order_by("start")
    # events = events.filter(seats__gt=Count("attendees"))
    if not user.is_staff:
        events = events.filter(circle__published=True)
    return events
