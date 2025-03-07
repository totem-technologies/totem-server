from datetime import datetime
from typing import List

from django.shortcuts import get_object_or_404
from django.urls import reverse
from ninja import Field, FilterSchema, ModelSchema, Router, Schema
from ninja.pagination import paginate
from ninja.params.functions import Query

from totem.users.schemas import UserSchema

from .filters import all_upcoming_recommended_events, events_by_month
from .models import Circle, CircleEvent

router = Router()


class SpaceSchema(ModelSchema):
    author: UserSchema

    class Meta:
        model = Circle
        fields = ["title", "slug", "date_created", "date_modified", "subtitle"]


class EventListSchema(ModelSchema):
    space: SpaceSchema
    url: str

    @staticmethod
    def resolve_url(obj: CircleEvent):
        return obj.get_absolute_url()

    @staticmethod
    def resolve_space(obj: CircleEvent):
        return obj.circle

    class Meta:
        model = CircleEvent
        fields = ["start", "slug", "date_created", "date_modified", "title"]


class EventsFilterSchema(FilterSchema):
    category: str | None
    author: str | None


class CategoryFilterSchema(Schema):
    name: str
    slug: str


class AuthorFilterSchema(Schema):
    name: str
    slug: str


class FilterOptionsSchema(Schema):
    categories: List[CategoryFilterSchema]
    authors: List[AuthorFilterSchema]


@router.get("/", response={200: List[EventListSchema]}, tags=["events"], url_name="events_list")
@paginate
def list_events(request, filters: EventsFilterSchema = Query()):
    return all_upcoming_recommended_events(request.user, category=filters.category, author=filters.author)


@router.get(
    "/filter-options",
    response={200: FilterOptionsSchema},
    tags=["events"],
    url_name="events_filter_options",
)
def filter_options(request):
    events = all_upcoming_recommended_events(request.user)
    # get distinct categories that have events
    categories = set(events.values_list("circle__categories__name", "circle__categories__slug").distinct())
    categories = [{"name": name, "slug": slug} for name, slug in categories if name]
    # get distinct authors that have events
    authors = set(events.values_list("circle__author__name", "circle__author__slug").distinct())
    authors = [{"name": name, "slug": slug} for name, slug in authors if name]
    return {"categories": categories, "authors": authors}


class EventDetailSchema(Schema):
    slug: str
    title: str
    space_title: str
    description: str
    price: int
    seats_left: int
    duration: int
    recurring: str
    subscribers: int
    start: datetime
    attending: bool
    open: bool
    started: bool
    cancelled: bool
    joinable: bool
    ended: bool
    rsvp_url: str
    join_url: str | None
    subscribe_url: str
    calLink: str
    subscribed: bool | None
    user_timezone: str | None


@router.get(
    "/event/{event_slug}",
    response={200: EventDetailSchema},
    tags=["events"],
    url_name="event_detail",
)
def event_detail(request, event_slug):
    event = get_object_or_404(CircleEvent, slug=event_slug)
    space = event.circle
    attending = event.attendees.filter(pk=request.user.pk).exists()
    start = event.start
    join_url = event.join_url(request.user) if attending else None
    subscribed = space.subscribed.contains(request.user) if request.user.is_authenticated else None
    ended = event.ended()
    return EventDetailSchema(
        slug=event.slug,
        title=event.title,
        space_title=space.title,
        description=space.content_html,
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
        subscribe_url=reverse("circles:subscribe", kwargs={"slug": space.slug}),
        subscribed=subscribed,
        user_timezone=str("UTC"),
    )


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
    events = events_by_month(request.user, filters.space_slug, filters.month, filters.year)
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
    events = all_upcoming_recommended_events(None)
    if filters.keeper_username:
        events = events.filter(circle__author__keeper_profile__username=filters.keeper_username)

    results: list[WebflowEventSchema] = []
    for event in events:
        circle = event.circle

        keeper_profile = getattr(circle.author, "keeper_profile", None)
        if not keeper_profile:
            continue

        image_url = circle.image.url if circle.image else None
        keeper_image_link = circle.author.profile_image.url if circle.author.profile_image else None
        join_link = request.build_absolute_uri(event.get_absolute_url())

        results.append(
            WebflowEventSchema(
                start=event.start.isoformat(),
                name=event.title or circle.title,
                keeper_name=circle.author.name,
                keeper_username=keeper_profile.username,
                join_link=join_link,
                image_link=image_url,
                keeper_image_link=keeper_image_link,
            )
        )

    return results


class NextEventSchema(Schema):
    slug: str
    start: str
    link: str
    title: str | None


class SpaceDetailSchema(Schema):
    slug: str
    title: str
    image_link: str | None
    description: str
    author: UserSchema
    nextEvent: NextEventSchema
    category: str | None


@router.get("/list", response={200: List[SpaceDetailSchema]}, tags=["spaces"], url_name="spaces_list")
def list_spaces(request):
    events = all_upcoming_recommended_events(None)
    spaces_set: set[str] = set()
    spaces = []
    for event in events:
        if event.circle.slug in spaces_set:
            continue
        spaces_set.add(event.circle.slug)
        circle: Circle = event.circle
        category = circle.categories.first()
        if category:
            category = category.name
        description = circle.short_description
        spaces.append(
            {
                "slug": circle.slug,
                "title": circle.title,
                "image_link": circle.image.url if circle.image else None,
                "description": description,
                "author": circle.author,
                "nextEvent": NextEventSchema(
                    slug=event.slug, start=event.start.isoformat(), title=event.title, link=event.get_absolute_url()
                ),
                "category": category,
            }
        )
    return spaces
