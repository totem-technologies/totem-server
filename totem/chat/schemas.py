import uuid
from datetime import datetime
from typing import Optional

from ninja import Schema
from pydantic import Field, field_validator


class MessageOutSchema(Schema):
    id: uuid.UUID
    room_id: uuid.UUID
    sender_id: int
    sender_name: str
    content: str
    created_at: datetime
    client_id: Optional[uuid.UUID] = None
    session_id: Optional[int] = None


class SendMessageInSchema(Schema):
    content: str = Field(..., max_length=10000)
    client_id: uuid.UUID
    session_id: Optional[int] = None


class ThreadOutSchema(Schema):
    id: uuid.UUID
    room_type: str
    session_id: Optional[int] = None
    unread_count: int
    last_message: Optional[MessageOutSchema] = None


class KeeperBulkMessageInSchema(Schema):
    user_ids: list[int]
    content: str = Field(..., max_length=10000)
    session_id: int

    @field_validator("user_ids")
    @classmethod
    def validate_user_list(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("The participant target list cannot be empty.")
        return v
