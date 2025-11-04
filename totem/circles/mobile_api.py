import datetime

from django.db import transaction
from django.db.models import Count, DateTimeField, ExpressionWrapper, F, Prefetch
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from ninja.errors import AuthorizationError
from ninja.pagination import paginate

from totem.circles.api import SpaceDetailSchema
from totem.circles.filters import (
    event_detail_schema,
    get_upcoming_events_for_spaces_list,
    space_detail_schema,
    space_schema,
    upcoming_recommended_events,
)
from totem.circles.models import Circle, CircleEvent, CircleEventException
from totem.circles.schemas import (
    EventDetailSchema,
    SpaceSchema,
    SummarySpacesSchema,
)
from totem.onboard.models import OnboardModel
from totem.users.models import User

spaces_router = Router(tags=["spaces"])


@spaces_router.post("/subscribe/{space_slug}", response={200: bool}, url_name="spaces_subscribe")
def subscribe_to_space(request: HttpRequest, space_slug: str):
    space = get_object_or_404(Circle, slug=space_slug, published=True)
    space.subscribe(request.user)
    return True


@spaces_router.delete("/subscribe/{space_slug}", response={200: bool}, url_name="spaces_unsubscribe")
def unsubscribe_to_space(request: HttpRequest, space_slug: str):
    space = get_object_or_404(Circle, slug=space_slug)
    space.unsubscribe(request.user)
    return True


@spaces_router.get("/subscribe", response={200: list[SpaceSchema]}, url_name="spaces_subscriptions")
def list_subscriptions(request: HttpRequest):
    circles = Circle.objects.filter(subscribed=request.user).select_related("author").prefetch_related("categories")
    return [space_schema(circle, request.user) for circle in circles]


@spaces_router.get("/", response={200: list[SpaceSchema]}, url_name="mobile_spaces_list")
@paginate
def list_spaces(request):
    circles = Circle.objects.filter(published=True, open=True).select_related("author").prefetch_related("categories")
    spaces: list[SpaceSchema] = [space_schema(circle, request.user) for circle in circles]
    return spaces


@spaces_router.get("/event/{event_slug}", response={200: EventDetailSchema}, url_name="event_detail")
def get_event_detail(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event = get_object_or_404(
        CircleEvent.objects.select_related("circle", "circle__author").prefetch_related(
            "circle__categories", "circle__subscribed", "attendees"
        ),
        slug=event_slug,
    )
    return event_detail_schema(event, user)


@spaces_router.get("/space/{space_slug}", response={200: SpaceDetailSchema}, url_name="spaces_detail")
def get_space_detail(request: HttpRequest, space_slug: str):
    user: User = request.user  # type: ignore
    space = get_object_or_404(
        Circle.objects.select_related("author").prefetch_related("categories", "subscribed"), slug=space_slug
    )
    return space_detail_schema(space, user)


@spaces_router.get("/keeper/{slug}/", response={200: list[SpaceSchema]}, url_name="keeper_spaces")
def get_keeper_spaces(request: HttpRequest, slug: str):
    user: User = request.user  # type: ignore

    circles = (
        Circle.objects.filter(author__slug=slug, published=True)
        .select_related("author")
        .prefetch_related("categories", "subscribed")
    )

    return [space_schema(circle, user) for circle in circles]


@spaces_router.get("/sessions/history", response={200: list[EventDetailSchema]}, url_name="sessions_history")
def get_sessions_history(request: HttpRequest):
    user: User = request.user  # type: ignore

    circle_history_query = (
        user.events_joined.filter(circle__published=True, cancelled=False)
        .select_related("circle", "circle__author")
        .prefetch_related("circle__categories", "circle__subscribed", "attendees")
        .order_by("-start")
    )
    circle_history = circle_history_query.all()[0:10]

    events = [event_detail_schema(event, user) for event in circle_history]

    return events


@spaces_router.get("/recommended", response={200: list[EventDetailSchema]}, url_name="recommended_spaces")
def get_recommended_spaces(request: HttpRequest, limit: int = 3, categories: list[str] | None = None):
    user: User = request.user  # type: ignore

    recommended_events = upcoming_recommended_events(user, categories=categories)[:limit]

    events = [event_detail_schema(event, user) for event in recommended_events]

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
    end_time_expression = ExpressionWrapper(
        F("start") + F("duration_minutes") * datetime.timedelta(minutes=1),
        output_field=DateTimeField(),
    )
    upcoming_events = (
        CircleEvent.objects.annotate(end_time=end_time_expression)
        .filter(attendees=user, cancelled=False, end_time__gt=timezone.now())
        .select_related("circle", "circle__author")
        .prefetch_related("circle__categories", "circle__subscribed", "attendees")
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
    for_you = [space_schema(event.circle, user) for event in recommended_events]

    events = get_upcoming_events_for_spaces_list()
    explore = [space_schema(event.circle, user) for event in events]

    return SummarySpacesSchema(
        upcoming=upcoming,
        for_you=for_you,
        explore=explore,
    )


@spaces_router.post(
    "/rsvp/{event_slug}",
    response={200: EventDetailSchema},
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

    # Refetch with prefetched relations for the schema
    event = (
        CircleEvent.objects.select_related("circle", "circle__author")
        .prefetch_related("circle__categories", "circle__subscribed", "attendees")
        .get(pk=event.pk)
    )
    return event_detail_schema(event, user)


@spaces_router.delete(
    "/rsvp/{event_slug}",
    response={200: EventDetailSchema},
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

    # Refetch with prefetched relations for the schema
    event = (
        CircleEvent.objects.select_related("circle", "circle__author")
        .prefetch_related("circle__categories", "circle__subscribed", "attendees")
        .get(pk=event.pk)
    )
    return event_detail_schema(event, user)
