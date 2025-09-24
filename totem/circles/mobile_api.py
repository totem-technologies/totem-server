from typing import List

from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from ninja.errors import AuthorizationError
from ninja.pagination import paginate

from totem.circles.api import NextEventSchema, SpaceDetailSchema
from totem.circles.filters import (
    event_detail_schema,
    get_upcoming_events_for_spaces_list,
    space_detail_schema,
    upcoming_recommended_events,
)
from totem.circles.models import Circle, CircleEvent, CircleEventException
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
        circle: Circle = event.circle

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
                "category": event.first_category,  # type: ignore
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
    upcoming_events = (
        CircleEvent.objects.filter(
            attendees=user,
            circle__published=True,
            cancelled=False,
            start__gte=timezone.now(),
        )
        .select_related("circle")
        .prefetch_related("circle__author", "circle__categories", "attendees")
        .annotate(attendee_count=Count("attendees", distinct=True))
        .order_by("start")
    )
    upcoming = [event_detail_schema(event, user) for event in upcoming_events]

    # The recommended spaces based on the user's onboarding.
    onboard_model = get_object_or_404(OnboardModel, user=user)
    categories_set = set()
    if onboard_model.hopes:
        for hope in onboard_model.hopes.split(","):
            name = hope.strip()
            if name:
                categories_set.add(name)
    # Add categories from user's previously joined spaces (single query)
    previous_category_names = (
        Circle.objects.filter(subscribed=user, published=True).values_list("categories__name", flat=True).distinct()
    )
    for name in previous_category_names:
        if name:
            categories_set.add(name)
    recommended_events = upcoming_recommended_events(user, categories=list(categories_set))
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


@spaces_router.post(
    "/rsvp/{event_slug}",
    response={200: bool},
    tags=["spaces"],
    url_name="rsvp_confirm",
)
def rsvp_confirm(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event = get_object_or_404(CircleEvent, slug=event_slug)
    try:
        with transaction.atomic():
            event.add_attendee(user)
            event.circle.subscribe(user)
    except CircleEventException as e:
        raise AuthorizationError(message=str(e))
    return True


@spaces_router.delete(
    "/rsvp/{event_slug}",
    response={200: bool},
    tags=["spaces"],
    url_name="rsvp_cancel",
)
def rsvp_cancel(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event = get_object_or_404(CircleEvent, slug=event_slug)
    try:
        event.remove_attendee(user)
    except CircleEventException as e:
        raise AuthorizationError(message=str(e))
    return True
