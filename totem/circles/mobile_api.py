from typing import List

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.pagination import paginate

from totem.circles.api import NextEventSchema, SpaceDetailSchema
from totem.circles.filters import event_detail_schema, get_upcoming_events_for_spaces_list
from totem.circles.models import Circle, CircleEvent
from totem.circles.schemas import EventDetailSchema, SpaceSchema
from totem.users.models import User

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
                    seats_left=event.seats_left(),  # Add seats_left to the event
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
    user: User = request.user  # type: ignore
    return event_detail_schema(event, user)


@spaces_router.get(
    "/keeper/{slug}/", response={200: List[SpaceDetailSchema]}, tags=["spaces"], url_name="keeper_spaces"
)
def get_keeper_spaces(request: HttpRequest, slug: str):
    circles = Circle.objects.filter(author__slug=slug, published=True)

    spaces = []
    for circle in circles:
        category = circle.categories.first()
        category_name = category.name if category else None

        nextEvent = circle.next_event()
        if nextEvent:
            spaces.append(
                SpaceDetailSchema(
                    slug=circle.slug,
                    title=circle.title,
                    image_link=circle.image.url if circle.image else None,
                    description=circle.short_description,
                    author=circle.author,
                    category=category_name,
                    nextEvent=NextEventSchema(
                        slug=nextEvent.slug,
                        start=nextEvent.start.isoformat(),
                        title=nextEvent.title,
                        link=nextEvent.get_absolute_url(),
                        seats_left=nextEvent.seats_left(),
                    ),
                )
            )

    return spaces


@spaces_router.get(
    "/sessions/history", response={200: List[EventDetailSchema]}, tags=["spaces"], url_name="sessions_history"
)
def get_sessions_history(request: HttpRequest):
    user: User = request.user  # type: ignore

    circle_history_query = user.events_joined.order_by("-start")
    circle_history = circle_history_query.all()[0:10]

    events = [
        event_detail_schema(event, user) for event in circle_history if event.circle.published and not event.cancelled
    ]

    return events
