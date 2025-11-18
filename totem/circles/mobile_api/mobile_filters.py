from django.db.models import Count, F, Prefetch, Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from totem.circles.mobile_api.mobile_schemas import (
    EventDetailSchema,
    MobileSpaceDetailSchema,
    NextEventSchema,
)
from totem.circles.models import Circle, CircleEvent
from totem.users.models import User


def get_upcoming_spaces_list() -> QuerySet[Circle]:
    return (
        Circle.objects.filter(published=True, events__start__gte=timezone.now())
        .distinct()
        .select_related("author")
        .prefetch_related(
            "categories",
            "subscribed",
            Prefetch(
                "events",
                queryset=CircleEvent.objects.filter(start__gte=timezone.now())
                .order_by("start")
                .prefetch_related("attendees"),
                to_attr="upcoming_events",
            ),
        )
        .annotate(subscriber_count=Count("subscribed", distinct=True))
    )


def upcoming_recommended_spaces(user: User | None, categories: list[str] | None = None, author: str | None = None):
    spaces = (
        Circle.objects.filter(events__start__gte=timezone.now())
        .distinct()
        .select_related("author")
        .prefetch_related(
            "categories",
            "subscribed",
            Prefetch(
                "events",
                queryset=CircleEvent.objects.filter(start__gte=timezone.now())
                .order_by("start")
                .prefetch_related("attendees"),
                to_attr="upcoming_events",
            ),
        )
        .annotate(subscriber_count=Count("subscribed", distinct=True))
    )
    if not user or not user.is_staff:
        spaces = spaces.filter(published=True)
    if categories:
        spaces = spaces.filter(Q(categories__slug__in=categories) | Q(categories__name__in=categories))
    if author:
        spaces = spaces.filter(author__slug=author)
    return spaces


def upcoming_recommended_events(user: User | None, categories: list[str] | None = None, author: str | None = None):
    events = (
        CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True)
        .select_related("circle")
        .prefetch_related(
            "circle__author",
            "circle__categories",
            "circle__subscribed",
            Prefetch(
                "circle__events",
                queryset=CircleEvent.objects.filter(start__gte=timezone.now())
                .order_by("start")
                .prefetch_related("attendees"),
                to_attr="upcoming_events",
            ),
        )
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


def event_detail_schema(event: CircleEvent, user: User):
    space: Circle = event.circle
    start = event.start

    if user.is_authenticated:
        if hasattr(space, "_prefetched_objects_cache") and "subscribed" in space._prefetched_objects_cache:
            subscribed = any(sub.pk == user.pk for sub in space.subscribed.all())
        else:
            subscribed = space.subscribed.filter(pk=user.pk).exists()
    else:
        subscribed = None
    ended = event.ended()

    attending = event.attendees.filter(pk=user.pk).exists()

    return EventDetailSchema(
        slug=event.slug,
        title=event.title,
        space=space_detail_schema(space, user),
        content=event.content_html,
        seats_left=event.seats_left(),
        duration=event.duration_minutes,
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


def next_event_schema(next_event: CircleEvent, user: User):
    seats_left = next_event.seats_left()

    if hasattr(next_event, "_prefetched_objects_cache") and "attendees" in next_event._prefetched_objects_cache:
        attending = any(attendee.pk == user.pk for attendee in next_event.attendees.all())
    else:
        attending = next_event.attendees.filter(pk=user.pk).exists()

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
        joinable=next_event.can_join(user),
    )


def space_detail_schema(circle: Circle, user: User):
    category = circle.categories.first()
    category_name = category.name if category else None

    if hasattr(circle, "upcoming_events"):
        upcoming_events = circle.upcoming_events
    else:
        upcoming_events = circle.events.filter(start__gte=timezone.now()).order_by("start")

    next_events = [next_event_schema(event, user) for event in upcoming_events]

    if hasattr(circle, "subscriber_count"):
        subscribers = circle.subscriber_count
    else:
        subscribers = circle.subscribed.count()

    return MobileSpaceDetailSchema(
        slug=circle.slug,
        title=circle.title,
        image_link=circle.image.url if circle.image else None,
        short_description=circle.short_description,
        content=circle.content_html,
        author=circle.author,
        category=category_name,
        subscribers=subscribers,
        price=circle.price,
        recurring=circle.recurring,
        next_events=next_events,
    )
