from datetime import datetime
from typing import List

from django.shortcuts import get_object_or_404
from django.urls import reverse
from ninja import Field, FilterSchema, ModelSchema, Router, Schema
from ninja.pagination import paginate
from ninja.params.functions import Query

from totem.users.models import User
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
    attendees: list[UserSchema]
    subscribed: bool | None
    user_timezone: str | None


@router.get(
    "/event/{event_slug}",
    response={200: EventDetailSchema},
    tags=["events"],
    url_name="event_detail",
)
def event_detail(request, event_slug):
    user: User = request.user
    event = get_object_or_404(CircleEvent, slug=event_slug)
    space = event.circle
    attending = event.attendees.filter(pk=request.user.pk).exists()
    start = event.start
    join_url = event.join_url(request.user) if attending else None
    subscribed = space.subscribed.contains(request.user) if request.user.is_authenticated else None
    ended = event.ended()
    tz = user.timezone if user.is_authenticated else "UTC"
    if attending and not ended:
        attendees = [a for a in event.attendees.all()]
    else:
        attendees = []
    return EventDetailSchema(
        slug=event.slug,
        title=space.title,
        description=space.content_html,
        price=space.price,
        seats_left=event.seats_left(),
        duration=event.duration_minutes,
        recurring=space.recurring,
        subscribers=space.subscribed.count(),
        start=start,
        attending=event.attendees.filter(pk=request.user.pk).exists(),
        attendees=attendees,
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
        user_timezone=str(tz),
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
