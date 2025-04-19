import datetime

from django.db.models import Count, F, Q
from django.utils import timezone

from totem.users.models import User

from .models import CircleEvent


def other_events_in_circle(user: User | None, event: CircleEvent, limit: int = 10):
    events = CircleEvent.objects.filter(circle=event.circle, start__gte=timezone.now(), cancelled=False).distinct()
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


def events_by_month(user: User | None, circle_slug: str, month: int, year: int):
    startDate = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    endDate = startDate + datetime.timedelta(days=32)
    events = CircleEvent.objects.filter(
        start__gte=startDate, start__lte=endDate, cancelled=False, circle__slug=circle_slug
    )
    if user and user.is_authenticated:
        # show users events they are already attending
        events = events.filter(Q(open=True, listed=True) | Q(attendees=user))
    else:
        events = events.filter(open=True, listed=True)
    events = events.order_by("start")
    if not user or not user.is_staff:
        events = events.filter(circle__published=True)
    return events


def all_upcoming_recommended_events(user: User | None, category: str | None = None, author: str | None = None):
    events = CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True)
    events = events.order_by("start")
    if not user or not user.is_staff:
        events = events.filter(circle__published=True)
    # are there any seats?
    events = events.annotate(attendee_count=Count("attendees")).filter(attendee_count__lt=F("seats"))
    # filter category
    if category:
        events = events.filter(circle__categories__slug=category) | events.filter(circle__categories__name=category)
    # filter author
    if author:
        events = events.filter(circle__author__slug=author)
    events = events.prefetch_related("circle__author")
    return events


def get_upcoming_events_for_spaces_list():
    """Get all upcoming events for spaces listing, including spaces with full events.

    Specifically designed for the spaces list API endpoint.
    Does NOT filter by seat availability, ensuring all spaces with upcoming events are shown.
    """
    return (
        CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True, circle__published=True)
        .select_related("circle")
        .prefetch_related("circle__author", "circle__categories")
        .annotate(attendee_count=Count("attendees"))
        .order_by("start")
    )


def all_upcoming_recommended_circles(user: User | None, category: str | None = None):
    events = CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, open=True, listed=True)
    events = events.order_by("start")
    if not user or not user.is_staff:
        events = events.filter(circle__published=True)
    # are there any seats?
    events = events.annotate(attendee_count=Count("attendees")).filter(attendee_count__lt=F("seats"))
    # filter category
    if category:
        events = events.filter(circle__categories__slug=category) | events.filter(circle__categories__name=category)
    events = events.prefetch_related("circle__author")
    return events


def upcoming_attending_events(user: User, limit: int = 10):
    # 60 minutes in the past
    past = timezone.now() - datetime.timedelta(minutes=60)
    return user.events_attending.filter(start__gte=past).filter(cancelled=False).order_by("start")[:limit]


def upcoming_events_by_author(user: User, author: User, exclude_event: CircleEvent | None = None):
    upcoming_events = CircleEvent.objects.filter(
        circle__author=author,
        start__gt=timezone.now(),
        cancelled=False,
        listed=True,
    ).order_by("start")

    if not user or not user.is_staff:
        upcoming_events = upcoming_events.filter(circle__published=True)

    if exclude_event:
        upcoming_events = upcoming_events.exclude(pk=exclude_event.pk)

    upcoming_events = upcoming_events.select_related("circle__author")
    return upcoming_events
