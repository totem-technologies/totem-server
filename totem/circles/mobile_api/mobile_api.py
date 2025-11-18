import datetime
from typing import List

from django.db import transaction
from django.db.models import Count, DateTimeField, ExpressionWrapper, F
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from ninja.errors import AuthorizationError
from ninja.pagination import paginate

from totem.circles.mobile_api.mobile_filters import (
    event_detail_schema,
    get_spaces_list,
    get_upcoming_spaces_list,
    space_detail_schema,
    upcoming_recommended_events,
    upcoming_recommended_spaces,
)
from totem.circles.mobile_api.mobile_schemas import (
    EventDetailSchema,
    MobileSpaceDetailSchema,
    SpaceSchema,
    SummarySpacesSchema,
)
from totem.circles.models import Circle, CircleEvent, CircleEventException
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


@spaces_router.get("/subscribe", response={200: List[SpaceSchema]}, url_name="spaces_subscriptions")
def list_subscriptions(request: HttpRequest):
    return Circle.objects.filter(subscribed=request.user)


@spaces_router.get("/", response={200: List[MobileSpaceDetailSchema]}, url_name="mobile_spaces_list")
@paginate
def list_spaces(request):
    spaces = get_spaces_list()
    return [space_detail_schema(space, request.user) for space in spaces]


@spaces_router.get("/event/{event_slug}", response={200: EventDetailSchema}, url_name="event_detail")
def get_event_detail(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event = get_object_or_404(CircleEvent, slug=event_slug)
    return event_detail_schema(event, user)


@spaces_router.get("/space/{space_slug}", response={200: MobileSpaceDetailSchema}, url_name="spaces_detail")
def get_space_detail(request: HttpRequest, space_slug: str):
    user: User = request.user  # type: ignore
    space = get_object_or_404(Circle, slug=space_slug)
    return space_detail_schema(space, user)


@spaces_router.get("/keeper/{slug}/", response={200: List[MobileSpaceDetailSchema]}, url_name="keeper_spaces")
def get_keeper_spaces(request: HttpRequest, slug: str):
    user: User = request.user  # type: ignore
    circles = get_upcoming_spaces_list().filter(author__slug=slug)
    return [space_detail_schema(circle, user) for circle in circles]


@spaces_router.get("/sessions/history", response={200: List[EventDetailSchema]}, url_name="sessions_history")
def get_sessions_history(request: HttpRequest):
    user: User = request.user  # type: ignore

    circle_history_query = user.events_joined.filter(circle__published=True, cancelled=False).order_by("-start")
    circle_history = circle_history_query.all()[0:10]

    events = [event_detail_schema(event, user) for event in circle_history]

    return events


@spaces_router.get("/recommended", response={200: List[EventDetailSchema]}, url_name="recommended_spaces")
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

    spaces_qs = get_upcoming_spaces_list()

    # The upcoming events that the user is subscribed to
    end_time_expression = ExpressionWrapper(
        F("start") + F("duration_minutes") * datetime.timedelta(minutes=1),
        output_field=DateTimeField(),
    )
    upcoming_events = (
        CircleEvent.objects.annotate(end_time=end_time_expression)
        .filter(attendees=user, cancelled=False, end_time__gt=timezone.now())
        .select_related("circle")
        .prefetch_related("circle__author", "circle__categories", "attendees", "circle__subscribed")
        .annotate(
            attendee_count=Count("attendees", distinct=True),
            subscriber_count=Count("circle__subscribed", distinct=True),
        )
        .order_by("start")
    )
    upcoming = [event_detail_schema(event, user) for event in upcoming_events]
    upcoming_circle_slugs = {event.circle.slug for event in upcoming_events}

    # The recommended spaces based on the user's onboarding.
    categories_set = set()
    try:
        onboard_model = OnboardModel.objects.get(user=user)
        if onboard_model.hopes:
            for hope in onboard_model.hopes.split(","):
                name = hope.strip()
                if name:
                    categories_set.add(name)
    except OnboardModel.DoesNotExist:
        # If no onboard model, just use empty categories set
        pass
    # Add categories from user's previously joined spaces (single query)
    previous_category_names = spaces_qs.filter(subscribed=user).values_list("categories__name", flat=True).distinct()
    categories_set.update(name for name in previous_category_names if name)
    recommended_spaces = upcoming_recommended_spaces(user, categories=list(categories_set))
    for_you = [
        space_detail_schema(space, user) for space in recommended_spaces if space.slug not in upcoming_circle_slugs
    ]

    spaces = spaces_qs
    explore = [space_detail_schema(space, user) for space in spaces if space.slug not in upcoming_circle_slugs]

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
    return event_detail_schema(event, user)
