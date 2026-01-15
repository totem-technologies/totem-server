from datetime import datetime
from typing import List

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Field, FilterSchema, Router, Schema
from ninja.pagination import paginate
from ninja.params.functions import Query

from totem.spaces.schemas import (
    EventDetailSchema,
    EventListSchema,
    EventsFilterSchema,
    FilterOptionsSchema,
    SpaceDetailSchema,
)
from totem.users.models import User

from .filters import (
    all_upcoming_recommended_sessions,
    get_upcoming_sessions_for_spaces_list,
    session_detail_schema,
    sessions_by_month,
    space_detail_schema,
)
from .models import Session, Space

router = Router()


@router.get("/", response={200: List[EventListSchema]}, tags=["events"], url_name="events_list")
@paginate
def list_events(request, filters: EventsFilterSchema = Query()):
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
    response={200: EventDetailSchema},
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


@router.get("/calendar", response={200: List[EventCalendarSchema]}, tags=["events"], url_name="event_calendar")
def upcoming_events(request, filters: EventCalendarFilterSchema = Query()):
    events = sessions_by_month(request.user, filters.space_slug, filters.month, filters.year)
    return [
        EventCalendarSchema(
            title=event.title, start=event.start.isoformat(), url=event.get_absolute_url(), slug=event.slug
        )
        for event in events
    ]


class WebflowEventsFilterSchema(FilterSchema):
    keeper_username: str | None = Field(
        default=None,
        description="Filter by Keeper's username",
    )


class WebflowEventSchema(Schema):
    start: str
    name: str
    keeper_name: str
    keeper_username: str
    join_link: str
    image_link: str | None
    keeper_image_link: str | None


@router.get(
    "/webflow/list_events",
    response={200: List[WebflowEventSchema]},
    tags=["events"],
    url_name="webflow_events_list",
    auth=None,
)
def webflow_events_list(request, filters: WebflowEventsFilterSchema = Query()):
    events = all_upcoming_recommended_sessions(None)
    if filters.keeper_username:
        events = events.filter(space__author__keeper_profile__username=filters.keeper_username)

    results: list[WebflowEventSchema] = []
    for event in events:
        space = event.space

        keeper_profile = getattr(space.author, "keeper_profile", None)
        if not keeper_profile:
            continue

        image_url = space.image.url if space.image else None
        keeper_image_link = space.author.profile_image.url if space.author.profile_image else None
        join_link = request.build_absolute_uri(event.get_absolute_url())

        results.append(
            WebflowEventSchema(
                start=event.start.isoformat(),
                name=event.title or space.title,
                keeper_name=space.author.name,
                keeper_username=keeper_profile.username,
                join_link=join_link,
                image_link=image_url,
                keeper_image_link=keeper_image_link,
            )
        )

    return results


@router.get("/list", response={200: List[SpaceDetailSchema]}, tags=["spaces"], url_name="spaces_list")
def list_spaces(request):
    # Get events with availability information
    events = get_upcoming_sessions_for_spaces_list()

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
