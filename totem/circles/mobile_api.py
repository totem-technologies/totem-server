from typing import List

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from ninja import Router
from ninja.pagination import paginate

from totem.circles.api import NextEventSchema, SpaceDetailSchema
from totem.circles.filters import get_upcoming_events_for_spaces_list
from totem.circles.models import Circle, CircleEvent
from totem.circles.schemas import EventDetailSchema, EventSpaceSchema, SpaceSchema

spaces_router = Router()


@spaces_router.post("/subscribe/{space_slug}", response={200: bool}, tags=["spaces"], url_name="spaces_subscribe")
def subscribe_to_space(request: HttpRequest, space_slug: str):
    space = get_object_or_404(Circle, slug=space_slug, published=True)
    space.subscribe(request.user)
    return True


@spaces_router.delete("/subscribe/{space_slug}", response={200: bool}, tags=["spaces"], url_name="spaces_unsubscribe")
def unsubscribe_to_space(request: HttpRequest, space_slug: str):
    space = get_object_or_404(Circle, slug=space_slug)
    space.unsubscribe(request.user)
    return True


@spaces_router.get("/subscribe", response={200: List[SpaceSchema]}, tags=["spaces"], url_name="spaces_subscriptions")
def list_subscriptions(request: HttpRequest):
    return Circle.objects.filter(subscribed=request.user)


@spaces_router.get("/spaces", response={200: List[SpaceDetailSchema]}, tags=["spaces"], url_name="mobile_spaces_list")
@paginate
def list_spaces(request):
    # Get events with availability information
    events = get_upcoming_events_for_spaces_list()

    # Build spaces list
    spaces_set = set()
    spaces = []

    for event in events:
        if event.circle.slug in spaces_set:
            continue

        spaces_set.add(event.circle.slug)
        circle = event.circle

        category = circle.categories.first()
        category_name = category.name if category else None

        # Calculate seats left for this event
        seats_left = max(0, event.seats - event.attendee_count)  # type: ignore

        spaces.append(
            {
                "slug": circle.slug,
                "title": circle.title,
                "image_link": circle.image.url if circle.image else None,
                "description": circle.short_description,
                "author": circle.author,
                "nextEvent": NextEventSchema(
                    slug=event.slug,
                    start=event.start.isoformat(),
                    title=event.title,
                    link=event.get_absolute_url(),
                    seats_left=seats_left,  # Add seats_left to the event
                ),
                "category": category_name,
            }
        )

    return spaces


@spaces_router.get(
    "/spaces/event/{event_slug}", response={200: EventDetailSchema}, tags=["spaces"], url_name="spaces_detail"
)
def get_space_detail(request: HttpRequest, event_slug: str):
    event = get_object_or_404(CircleEvent, slug=event_slug)
    space: Circle = event.circle
    attending = event.attendees.filter(pk=request.user.pk).exists()
    start = event.start
    join_url = event.join_url(request.user) if attending else None
    subscribed = space.subscribed.contains(request.user) if request.user.is_authenticated else None
    ended = event.ended()
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
        attending=event.attendees.filter(pk=request.user.pk).exists(),
        open=event.open,
        started=event.started(),
        cancelled=event.cancelled,
        joinable=event.can_join(request.user),
        ended=ended,
        rsvp_url=reverse("circles:rsvp", kwargs={"event_slug": event.slug}),
        join_url=join_url,
        calLink=event.cal_link(),
        subscribe_url=reverse("mobile-api:spaces_subscribe", kwargs={"space_slug": space.slug}),
        subscribed=subscribed,
        user_timezone=str("UTC"),
    )


@spaces_router.get("/keeper/{slug}/", response={200: List[SpaceSchema]}, tags=["spaces"], url_name="keeper_spaces")
def get_keeper_spaces(request: HttpRequest, slug: str):
    return Circle.objects.filter(author__slug=slug, published=True)
