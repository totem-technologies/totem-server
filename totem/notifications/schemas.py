from datetime import datetime
from enum import Enum

from ninja import Schema
from pydantic import Field


class FCMFIDRegisterSchema(Schema):
    fid: str


class FCMFIDResponseSchema(Schema):
    fid: str
    active: bool
    created_at: datetime


class NotificationType(str, Enum):
    SESSION_STARTING = "session_starting"
    SESSION_ADVERTISEMENT = "session_advertisement"
    MISSED_SESSION = "missed_session"


class SessionNotificationPayload(Schema):
    type: NotificationType
    space_slug: str = Field(min_length=1, max_length=50, pattern=r"^[-a-zA-Z0-9_]+$")
    session_slug: str = Field(min_length=1, max_length=50, pattern=r"^[-a-zA-Z0-9_]+$")
