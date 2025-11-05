from datetime import datetime
from enum import Enum

from ninja import FilterSchema, ModelSchema, Schema

from totem.circles.models import Circle, CircleEvent
from totem.users.schemas import PublicUserSchema


class MeetingProviderEnum(str, Enum):
    GOOGLE_MEET = "google_meet"
    LIVEKIT = "livekit"


class NextEventSchema(Schema):
    slug: str
    start: datetime
    link: str
    title: str | None
    seats_left: int
    duration: int
    meeting_provider: MeetingProviderEnum
    cal_link: str
    attending: bool
    cancelled: bool
    open: bool
    joinable: bool


class SpaceSchema(ModelSchema):
    author: PublicUserSchema
    next_event: NextEventSchema | None
    image_url: str | None
    categories: list[str]

    @staticmethod
    def resolve_image_url(obj: Circle):
        return obj.image.url if obj.image else None

    @staticmethod
    def resolve_categories(obj: Circle):
        return [category.name for category in obj.categories.all()]

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
    def resolve_space(obj: CircleEvent, context):
        from totem.circles.filters import space_schema

        user = context.get("request").user if context.get("request") else None
        return space_schema(obj.circle, user)

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
    categories: list[CategoryFilterSchema]
    authors: list[AuthorFilterSchema]


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
            "short_description",
            "recurring",
            "image",
            "content",
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
    cal_link: str
    subscribed: bool | None
    user_timezone: str | None
    meeting_provider: MeetingProviderEnum


class SpaceDetailSchema(Schema):
    slug: str
    title: str
    image_link: str | None
    short_description: str
    content: str
    author: PublicUserSchema
    category: str | None
    subscribers: int
    recurring: str | None
    price: int
    next_events: list[NextEventSchema]


class SummarySpacesSchema(Schema):
    upcoming: list[EventDetailSchema]
    for_you: list[SpaceSchema]
    explore: list[SpaceSchema]
