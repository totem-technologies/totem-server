from django.db.models import Count, F, OuterRef, Q, QuerySet, Subquery
from django.urls import reverse
from django.utils import timezone

from totem.circles.mobile_api.mobile_schemas import (
    EventDetailSchema,
    EventSpaceSchema,
    NextEventSchema,
    SpaceDetailSchema,
)
from totem.circles.models import Circle, CircleCategory, CircleEvent
from totem.users.models import User


def get_upcoming_spaces_list() -> QuerySet[Circle]:
    return (
        Circle.objects.filter(published=True, events__start__gte=timezone.now())
        .distinct()
        .prefetch_related("categories", "subscribed")
        .annotate(subscriber_count=Count("subscribed", distinct=True))
    )


def upcoming_recommended_events(user: User | None, categories: list[str] | None = None, author: str | None = None):
    events = (
        CircleEvent.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True)
        .select_related("circle")
        .prefetch_related("circle__author", "circle__categories", "circle__subscribed")
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
        .select_related("circle")
        .prefetch_related("circle__author", "circle__categories", "circle__subscribed")
        .annotate(
            attendee_count=Count("attendees", distinct=True),
            subscriber_count=Count("circle__subscribed", distinct=True),
            first_category=Subquery(first_category_subquery),
        )
        .order_by("start")
    )


def event_detail_schema(event: CircleEvent, user: User):
    space: Circle = event.circle
    start = event.start
    subscribed = space.subscribed.contains(user) if user.is_authenticated else None
    ended = event.ended()

    attending = event.attendees.filter(pk=user.pk).exists()

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
        subscribers=space.subscribed.count(),
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


def space_detail_schema(circle: Circle, user: User, event: CircleEvent | None = None):
    category = circle.categories.first()
    category_name = category.name if category else None

    next_event = event or circle.next_event()
    next_event_schema: NextEventSchema | None = None
    if next_event:
        seats_left = next_event.seats_left()
        next_event_schema = NextEventSchema(
            slug=next_event.slug,
            start=next_event.start,
            title=next_event.title,
            link=next_event.get_absolute_url(),
            seats_left=seats_left,
            duration=next_event.duration_minutes,
            meeting_provider=next_event.meeting_provider,
            cal_link=next_event.cal_link(),
            attending=next_event.attendees.filter(pk=user.pk).exists(),
            cancelled=next_event.cancelled,
            open=next_event.open,
            joinable=next_event.can_join(user),
        )

    return SpaceDetailSchema(
        slug=circle.slug,
        title=circle.title,
        image_link=circle.image.url if circle.image else None,
        short_description=circle.short_description,
        content=circle.content_html,
        author=circle.author,
        category=category_name,
        next_event=next_event_schema,
        subscribers=circle.subscribed.count(),
        price=circle.price,
        recurring=circle.recurring,
    )
