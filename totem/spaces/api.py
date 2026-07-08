from datetime import datetime

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Field, FilterSchema, Router, Schema
from ninja.pagination import paginate
from ninja.params.functions import Query
from ninja.security import django_auth

from totem.spaces.schemas import (
    FilterOptionsSchema,
    SessionDetailSchema,
    SessionListSchema,
    SessionsFilterSchema,
    SpaceDetailSchema,
    SummarySpacesSchema,
)
from totem.users.models import User

from .filters import (
    all_upcoming_recommended_sessions,
    get_upcoming_sessions_for_spaces_list,
    session_detail_schema,
    sessions_by_month,
    space_detail_schema,
    spaces_summary_data,
)
from .models import Session, Space

router = Router()


@router.get("/", response={200: list[SessionListSchema]}, tags=["events"], url_name="events_list")
@paginate
def list_events(request, filters: SessionsFilterSchema = Query()):
    return all_upcoming_recommended_sessions(request.user, category=filters.category, author=filters.author)


@router.get(
    "/filter-options",
    response={200: FilterOptionsSchema},
    tags=["events"],
    url_name="events_filter_options",
)
def filter_options(request):
    events = all_upcoming_recommended_sessions(request.user)
    # get distinct categories that have events
    categories = set(events.values_list("space__categories__name", "space__categories__slug").distinct())
    categories = [{"name": name, "slug": slug} for name, slug in categories if name]
    # get distinct authors that have events
    authors = set(events.values_list("space__author__name", "space__author__slug").distinct())
    authors = [{"name": name, "slug": slug} for name, slug in authors if name]
    return {"categories": categories, "authors": authors}


@router.get(
    "/event/{event_slug}",
    response={200: SessionDetailSchema},
    tags=["events"],
    url_name="event_detail",
)
def event_detail(request: HttpRequest, event_slug: str):
    event = get_object_or_404(Session, slug=event_slug)
    user: User = request.user  # type: ignore

    return session_detail_schema(event, user)


class EventCalendarSchema(Schema):
    title: str
    start: str
    slug: str
    url: str


class EventCalendarFilterSchema(FilterSchema):
    space_slug: str = Field(default="", description="Space slug")
    month: int = Field(default=datetime.now().month, description="Month of the year, 1-12", gt=0, lt=13)
    year: int = Field(default=datetime.now().year, description="Year of the month, e.g. 2024", gt=1000, lt=3000)


@router.get("/calendar", response={200: list[EventCalendarSchema]}, tags=["events"], url_name="event_calendar")
def upcoming_events(request, filters: EventCalendarFilterSchema = Query()):
    events = sessions_by_month(request.user, filters.space_slug, filters.month, filters.year)
    return [
        EventCalendarSchema(
            title=event.title, start=event.start.isoformat(), url=event.get_absolute_url(), slug=event.slug
        )
        for event in events
    ]


@router.get(
    "/summary",
    response={200: SummarySpacesSchema},
    tags=["spaces"],
    url_name="spaces_summary",
    auth=django_auth,
)
def spaces_summary(request: HttpRequest):
    user: User = request.user  # type: ignore
    data = spaces_summary_data(user)
    # The dashboard renders at most 4 recommendation cards; cap serialization
    # with a little headroom rather than paying for the whole catalog.
    limit = 8
    return SummarySpacesSchema(
        upcoming=[session_detail_schema(session, user) for session in data.upcoming],
        for_you=[space_detail_schema(space, user) for space in data.for_you[:limit]],
        explore=[space_detail_schema(space, user) for space in data.explore[:limit]],
    )


@router.get("/list", response={200: list[SpaceDetailSchema]}, tags=["spaces"], url_name="spaces_list")
def list_spaces(request):
    # Get events with availability information
    events = get_upcoming_sessions_for_spaces_list(request.user)

    # Build spaces list
    spaces_set = set()
    spaces = []

    for event in events:
        if event.space.slug in spaces_set:
            continue

        spaces_set.add(event.space.slug)
        space: Space = event.space

        spaces.append(space_detail_schema(space, request.user))

    return spaces
