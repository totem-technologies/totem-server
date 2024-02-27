from django.db.models import Count, F, Q
from django.utils import timezone

from totem.users.models import User

from .models import CircleEvent


def other_events_in_circle(user: User | None, event: CircleEvent, limit: int = 10):
    events = CircleEvent.objects.filter(circle=event.circle, start__gte=timezone.now(), cancelled=False)
    if user and user.is_authenticated:
        # show users events they are already attending
        events = events.filter(Q(open=True, listed=True) | Q(attendees=user))
    else:
        events = events.filter(open=True, listed=True)
    events = events.exclude(slug=event.slug)
    events = events.order_by("start")
    if not user or not user.is_staff:
        events = events.filter(circle__published=True)

    return events[:limit]


def all_upcoming_recommended_events(user: User | None, category: str | None = None, limit: int = 10):
    events = CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, open=True, listed=True)
    events = events.order_by("start")
    if not user or not user.is_staff:
        events = events.filter(circle__published=True)
    if user and user.is_authenticated:
        events = events.exclude(attendees=user)
        events = events.exclude(joined=user)
    # are there any seats?
    events = events.annotate(attendee_count=Count("attendees")).filter(attendee_count__lt=F("seats"))
    # filter category
    if category:
        events = events.filter(circle__categories__slug=category) | events.filter(circle__categories__name=category)
    events = events.prefetch_related("circle__author")
    return events[:limit]


def all_upcoming_recommended_circles(user: User | None, category: str | None = None, limit: int = 10):
    events = CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, open=True, listed=True)
    events = events.order_by("start")
    if not user or not user.is_staff:
        events = events.filter(circle__published=True)
    if user and user.is_authenticated:
        events = events.exclude(attendees=user)
        events = events.exclude(joined=user)
    # are there any seats?
    events = events.annotate(attendee_count=Count("attendees")).filter(attendee_count__lt=F("seats"))
    # filter category
    if category:
        events = events.filter(circle__categories__slug=category) | events.filter(circle__categories__name=category)
    events = events.prefetch_related("circle__author")
    return events[:limit]


def upcoming_attending_events(user: User, limit: int = 10):
    # 60 minutes in the past
    past = timezone.now() - timezone.timedelta(minutes=60)
    return user.events_attending.filter(start__gte=past).filter(cancelled=False).order_by("start")[:limit]
