from datetime import datetime
from enum import Enum

from ninja import FilterSchema, ModelSchema, Schema

from totem.spaces.models import Session, Space
from totem.users.schemas import PublicUserSchema


class SpaceSchema(ModelSchema):
    author: PublicUserSchema

    class Meta:
        model = Space
        fields = ["title", "slug", "date_created", "date_modified", "subtitle"]


class SessionListSchema(ModelSchema):
    space: SpaceSchema
    url: str

    @staticmethod
    def resolve_url(obj: Session):
        return obj.get_absolute_url()

    @staticmethod
    def resolve_space(obj: Session):
        return obj.space

    class Meta:
        model = Session
        fields = ["start", "slug", "date_created", "date_modified", "title"]


class SessionsFilterSchema(FilterSchema):
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


class SessionSpaceSchema(ModelSchema):
    author: PublicUserSchema

    def description(self, obj: Space):
        return obj.content_html

    class Meta:
        model = Space
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
            "content",
        ]


class MeetingProviderEnum(str, Enum):
    GOOGLE_MEET = "google_meet"
    LIVEKIT = "livekit"


class SessionDetailSchema(Schema):
    slug: str
    title: str
    space: SessionSpaceSchema
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


class NextSessionSchema(Schema):
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


class SpaceDetailSchema(Schema):
    slug: str
    title: str
    image_link: str | None
    short_description: str
    content: str
    author: PublicUserSchema
    next_event: NextSessionSchema | None
    category: str | None
    subscribers: int
    recurring: str | None
    price: int


class SummarySpacesSchema(Schema):
    upcoming: list[SessionDetailSchema]
    for_you: list[SpaceDetailSchema]
    explore: list[SpaceDetailSchema]
