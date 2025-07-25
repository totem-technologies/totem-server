from typing import List

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.pagination import paginate

from totem.circles.api import NextEventSchema, SpaceDetailSchema
from totem.circles.filters import (
    event_detail_schema,
    get_upcoming_events_for_spaces_list,
    space_detail_schema,
    upcoming_recommended_events,
)
from totem.circles.models import Circle, CircleEvent
from totem.circles.schemas import EventDetailSchema, SpaceSchema, SummarySpacesSchema
from totem.onboard.models import OnboardModel
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


@spaces_router.get("/", response={200: List[SpaceDetailSchema]}, tags=["spaces"], url_name="mobile_spaces_list")
@paginate
def list_spaces(request):
    events = get_upcoming_events_for_spaces_list()

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
                    seats_left=event.seats_left(),
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
        nextEvent = circle.next_event()
        if nextEvent:
            spaces.append(space_detail_schema(nextEvent))

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


@spaces_router.get(
    "/recommended", response={200: List[EventDetailSchema]}, tags=["spaces"], url_name="recommended_spaces"
)
def get_recommended_spaces(request: HttpRequest, limit: int = 3, categories: list[str] | None = None):
    user: User = request.user  # type: ignore

    recommended_events = upcoming_recommended_events(user, categories=categories)[:limit]

    events = [
        event_detail_schema(event, user)
        for event in recommended_events
        if event.circle.published and not event.cancelled
    ]

    return events


@spaces_router.get(
    "/summary",
    response={200: SummarySpacesSchema},
    tags=["spaces"],
    url_name="spaces_summary",
)
def get_spaces_summary(request: HttpRequest):
    user: User = request.user  # type: ignore

    # The upcoming events that the user is subscribed to
    upcoming_events = CircleEvent.objects.filter(
        attendees=user,
        circle__published=True,
    ).order_by("start")
    upcoming = [event_detail_schema(event, user) for event in upcoming_events]

    # The recommended spaces based on the user's onboarding.
    onboard_model = get_object_or_404(OnboardModel, user=user)
    categories = []
    if onboard_model.hopes:
        print(onboard_model.hopes.split(", "))
        for hope in onboard_model.hopes.split(", "):
            categories.append(hope)
    # Add categories from user's previously joined spaces
    previous_spaces = Circle.objects.filter(subscribed=user, published=True).distinct()
    for circle in previous_spaces:
        category = circle.categories.first()
        category_name = category.name if category else None
        if category_name and category_name not in categories:
            categories.append(category_name)
    recommended_events = upcoming_recommended_events(user, categories=categories)
    for_you = [
        space_detail_schema(event) for event in recommended_events if event.circle.published and not event.cancelled
    ]

    spaces = get_upcoming_events_for_spaces_list()
    explore = [space_detail_schema(space) for space in spaces if space.circle.published and not space.cancelled]

    return SummarySpacesSchema(
        upcoming=upcoming,
        for_you=for_you,
        explore=explore,
    )
