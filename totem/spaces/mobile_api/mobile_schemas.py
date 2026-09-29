from datetime import datetime
from enum import Enum

from ninja import Field, ModelSchema, Schema

from totem.spaces.models import Session, SessionFeedbackOptions, SessionPrompt, Space
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


class MeetingProviderEnum(str, Enum):
    GOOGLE_MEET = "google_meet"
    LIVEKIT = "livekit"


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


class MobileSpaceDetailSchema(Schema):
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
    next_events: list[NextSessionSchema]


class SessionDetailSchema(Schema):
    slug: str
    title: str
    space: MobileSpaceDetailSchema
    content: str
    seats_left: int
    duration: int
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


class SessionPromptSchema(ModelSchema):
    class Meta:
        model = SessionPrompt
        fields = ["id", "prompt", "position"]


class SessionPromptsSchema(Schema):
    prompts: list[SessionPromptSchema]
    previous_prompt: SessionPromptSchema | None
    current_prompt: SessionPromptSchema | None
    next_prompt: SessionPromptSchema | None


class SessionPromptUpdateSchema(Schema):
    id: int | None = None
    prompt: str = Field(min_length=1, max_length=1000)


class SessionPromptsUpdateSchema(Schema):
    prompts: list[SessionPromptUpdateSchema]


class SessionPromptSelectionSchema(Schema):
    prompt_id: int | None


class SessionConflictSchema(Schema):
    message: str
    conflicting_sessions: list[SessionDetailSchema]


class SummarySpacesSchema(Schema):
    upcoming: list[SessionDetailSchema]
    for_you: list[MobileSpaceDetailSchema]
    explore: list[MobileSpaceDetailSchema]


class SessionFeedbackSchema(Schema):
    feedback: SessionFeedbackOptions
    message: str | None = None


class ResolveConflictsSchema(Schema):
    conflicting_session_slugs: list[str]
