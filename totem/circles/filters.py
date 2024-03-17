from django.db.models import Count, F, OuterRef, Q, Subquery
from django.utils import timezone

from totem.users.models import User

from .models import Circle, CircleEvent


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


def all_upcoming_recommended_events(user: User | None, category: str | None = None, limit: int = 10):
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
    return events[:limit]


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
    past = timezone.now() - timezone.timedelta(minutes=60)
    return user.events_attending.filter(start__gte=past).filter(cancelled=False).order_by("start")[:limit]


def upcoming_events_by_author(user: User, author: User, exclude_circle: Circle | None = None):
    # Subquery to get the next upcoming CircleEvent for each Circle
    next_event_subquery = (
        CircleEvent.objects.filter(
            circle=OuterRef("pk"),
            circle__author=author,
            start__gt=timezone.now(),
            cancelled=False,
            open=True,
            listed=True,
        )
        .order_by("start")
        .values("id")[:1]
    )

    # Annotate each Circle with the id of the next upcoming CircleEvent
    circles = Circle.objects.filter(author=author).annotate(next_event_id=Subquery(next_event_subquery))

    # Filter out Circles without an upcoming CircleEvent
    circles_with_upcoming_event = circles.exclude(next_event_id__isnull=True)

    if not user or not user.is_staff:
        circles_with_upcoming_event = circles_with_upcoming_event.filter(published=True)

    if exclude_circle:
        circles_with_upcoming_event = circles_with_upcoming_event.exclude(pk=exclude_circle.pk)

    # Get the CircleEvent objects
    upcoming_events = CircleEvent.objects.filter(id__in=circles_with_upcoming_event.values("next_event_id")).order_by(
        "start"
    )
    upcoming_events = upcoming_events.prefetch_related("circle__author")
    return upcoming_events
