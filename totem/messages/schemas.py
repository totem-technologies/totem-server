from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ninja import Field, Schema

from totem.users.schemas import ProfileAvatarTypeEnum

from .services import MAX_SESSION_MESSAGE_RECIPIENTS


class MessagePeerSchema(Schema):
    # Deliberately narrow privacy projection for messaging peers.
    slug: str
    name: str
    profile_image: str | None
    profile_avatar_seed: UUID
    profile_avatar_type: ProfileAvatarTypeEnum


class MessagePreviewSchema(Schema):
    id: UUID
    sender_slug: str
    text: str
    created_at: datetime
    is_mine: bool


class ConversationSummarySchema(Schema):
    id: UUID
    peer: MessagePeerSchema
    last_message: MessagePreviewSchema | None
    unread_count: int
    updated_at: datetime


class ConversationPageSchema(Schema):
    items: list[ConversationSummarySchema]
    next_cursor: str | None
    total_unread_count: int


class OpenConversationSchema(Schema):
    recipient_slug: str


class RecipientDirectoryKind(StrEnum):
    KEEPERS = "keepers"
    PARTICIPANTS = "participants"


class KeeperRecipientSchema(Schema):
    profile: MessagePeerSchema
    existing_conversation_id: UUID | None
    can_start_direct: bool


class ParticipantRecipientSchema(KeeperRecipientSchema):
    session_slug: str
    session_title: str
    session_start: datetime


class RecipientDirectorySchema(Schema):
    """The first ordered keepers page is the recommendation source."""

    kind: RecipientDirectoryKind
    keepers: list[KeeperRecipientSchema]
    participants: list[ParticipantRecipientSchema]
    next_cursor: str | None


class MessageSchema(Schema):
    id: UUID
    sender_slug: str
    text: str
    client_message_id: UUID | None
    created_at: datetime
    cursor: str
    is_mine: bool


class MessagePageSchema(Schema):
    """Initial and before pages are newest-first; after pages are oldest-first."""

    items: list[MessageSchema]
    next_before: str | None
    next_after: str | None
    has_more: bool


class SendMessageSchema(Schema):
    text: str
    client_message_id: UUID | None = None


class MarkReadSchema(Schema):
    last_read_message_id: UUID


class SyncPageSchema(Schema):
    items: list[ConversationSummarySchema]
    next_cursor: str | None
    total_unread_count: int


class SessionParticipantSchema(Schema):
    profile: MessagePeerSchema
    sessions_count: int


class SessionParticipantPageSchema(Schema):
    items: list[SessionParticipantSchema]
    next_cursor: str | None


class SendSessionMessagesSchema(Schema):
    recipient_slugs: list[str] = Field(max_length=MAX_SESSION_MESSAGE_RECIPIENTS)
    text: str
    client_request_id: UUID


class SessionMessageRecipientResultSchema(Schema):
    recipient_slug: str
    conversation_id: UUID
    message_id: UUID


class SessionMessageResultSchema(Schema):
    requested_count: int
    sent_count: int
    recipients: list[SessionMessageRecipientResultSchema]
