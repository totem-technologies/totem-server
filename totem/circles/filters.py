import datetime

from django.db.models import Count, F, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone

from totem.circles.schemas import EventDetailSchema, EventSpaceSchema, NextEventSchema, SpaceDetailSchema, SpaceSchema
from totem.users.models import User
from totem.users.schemas import PublicUserSchema

from .models import Circle, CircleCategory, CircleEvent


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


def upcoming_recommended_events(user: User | None, categories: list[str] | None = None, author: str | None = None):
    events = (
        CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True)
        .select_related("circle", "circle__author")
        .prefetch_related("circle__categories", "circle__subscribed", "attendees")
        .annotate(
            attendee_count=Count("attendees", distinct=True),
            subscriber_count=Count("circle__subscribed", distinct=True),
        )
        .order_by("start")
    )
    if not user or not user.is_staff:
        events = events.filter(circle__published=True)
    # are there any seats?
    events = events.filter(attendee_count__lt=F("seats"))
    # filter category
    if categories:
        events = events.filter(Q(circle__categories__slug__in=categories) | Q(circle__categories__name__in=categories))
    # filter author
    if author:
        events = events.filter(circle__author__slug=author)
    return events


def get_upcoming_events_for_spaces_list():
    """Get all upcoming events for spaces listing, including spaces with full events.

    Specifically designed for the spaces list API endpoint.
    Does NOT filter by seat availability, ensuring all spaces with upcoming events are shown.
    """
    first_category_subquery = CircleCategory.objects.filter(circle=OuterRef("pk")).values("name")[:1]
    return (
        CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True, circle__published=True)
        .select_related("circle", "circle__author")
        .prefetch_related("circle__categories", "circle__subscribed", "attendees")
        .annotate(
            attendee_count=Count("attendees", distinct=True),
            subscriber_count=Count("circle__subscribed", distinct=True),
            first_category=Subquery(first_category_subquery),
        )
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


def event_detail_schema(event: CircleEvent, user: User):
    space: Circle = event.circle
    start = event.start

    subscribed = space.subscribed.filter(pk=user.pk).exists() if user.is_authenticated else None
    ended = event.ended()

    attending = event.attendees.filter(pk=user.pk).exists()

    subscribers_count = getattr(event, "subscriber_count", space.subscribed.count())

    return EventDetailSchema(
        slug=event.slug,
        title=event.title,
        space_title=space.title,
        space=EventSpaceSchema.from_orm(space),
        description=event.content_html,
        price=space.price,
        seats_left=event.seats_left(),
        duration=event.duration_minutes,
        recurring=space.recurring,
        subscribers=subscribers_count,
        start=start,
        attending=attending,
        open=event.open,
        started=event.started(),
        cancelled=event.cancelled,
        joinable=event.can_join(user),
        ended=ended,
        rsvp_url=reverse("circles:rsvp", kwargs={"event_slug": event.slug}),
        join_url=reverse("circles:join", kwargs={"event_slug": event.slug}),
        cal_link=event.cal_link(),
        subscribe_url=reverse("mobile-api:spaces_subscribe", kwargs={"space_slug": space.slug}),
        subscribed=subscribed,
        user_timezone=str("UTC"),
        meeting_provider=event.meeting_provider,
    )


def next_event_schema(next_event: CircleEvent | None, user: User | None) -> NextEventSchema | None:
    if next_event is None:
        return None
    seats_left = next_event.seats_left()
    attending = next_event.attendees.filter(pk=user.pk).exists() if user else False
    return NextEventSchema(
        slug=next_event.slug,
        start=next_event.start,
        title=next_event.title,
        link=next_event.get_absolute_url(),
        seats_left=seats_left,
        duration=next_event.duration_minutes,
        meeting_provider=next_event.meeting_provider,
        cal_link=next_event.cal_link(),
        attending=attending,
        cancelled=next_event.cancelled,
        open=next_event.open,
        joinable=next_event.can_join(user) if user else False,
    )


def space_detail_schema(circle: Circle, user: User, event: CircleEvent | None = None):
    category = circle.categories.first()
    category_name = category.name if category else None

    past = timezone.now() - datetime.timedelta(minutes=60)
    next_events = (
        CircleEvent.objects.filter(circle=circle, start__gte=past, cancelled=False)
        .select_related("circle")
        .prefetch_related("attendees")
        .order_by("start")
    )
    next_event_schemas: list[NextEventSchema] = [next_event_schema(event, user) for event in next_events]

    return SpaceDetailSchema(
        slug=circle.slug,
        title=circle.title,
        image_link=circle.image.url if circle.image else None,
        short_description=circle.short_description,
        content=circle.content_html,
        author=circle.author,
        category=category_name,
        subscribers=circle.subscribed.count(),
        price=circle.price,
        recurring=circle.recurring,
        next_events=next_event_schemas,
    )


def space_schema(circle: Circle, user: User | None) -> SpaceSchema:
    return SpaceSchema(
        title=circle.title,
        slug=circle.slug,
        date_created=circle.date_created,
        date_modified=circle.date_modified,
        subtitle=circle.subtitle,
        author=PublicUserSchema.from_orm(circle.author),
        next_event=next_event_schema(circle.next_event(), user),
    )
