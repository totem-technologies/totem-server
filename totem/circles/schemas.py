from datetime import datetime
from typing import List

from ninja import FilterSchema, ModelSchema, Schema

from totem.circles.models import Circle, CircleEvent
from totem.users.schemas import PublicUserSchema


class SpaceSchema(ModelSchema):
    author: PublicUserSchema

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


class EventSpaceSchema(ModelSchema):
    author: PublicUserSchema

    def description(self, obj: Circle):
        return obj.content_html

    class Meta:
        model = Circle
        fields = [
            "title",
            "slug",
            "date_created",
            "date_modified",
            "subtitle",
            "categories",
            "short_description",
            "recurring",
            "image",
        ]


class EventDetailSchema(Schema):
    slug: str
    title: str
    space: EventSpaceSchema
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


class NextEventSchema(Schema):
    slug: str
    start: str
    link: str
    title: str | None
    seats_left: int


class SpaceDetailSchema(Schema):
    slug: str
    title: str
    image_link: str | None
    description: str
    author: PublicUserSchema
    nextEvent: NextEventSchema
    category: str | None


class SummarySpacesSchema(Schema):
    upcoming: List[EventDetailSchema]
    for_you: List[SpaceDetailSchema]
    explore: List[SpaceDetailSchema]


class LivekitTokenResponseSchema(Schema):
    token: str
