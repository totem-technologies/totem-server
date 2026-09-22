from typing import NoReturn
from uuid import UUID

from django.http import Http404, HttpRequest
from ninja import Router, Status
from ninja.errors import ValidationError

from totem.users.models import User
from totem.users.schemas import ProfileAvatarTypeEnum

from .models import Message
from .schemas import (
    ConversationPageSchema,
    ConversationSummarySchema,
    KeeperRecipientSchema,
    MarkReadSchema,
    MessagePageSchema,
    MessagePeerSchema,
    MessagePreviewSchema,
    MessageSchema,
    OpenConversationSchema,
    ParticipantRecipientSchema,
    RecipientDirectoryKind,
    RecipientDirectorySchema,
    SendMessageSchema,
    SendSessionMessagesSchema,
    SessionMessageRecipientResultSchema,
    SessionMessageResultSchema,
    SessionParticipantPageSchema,
    SessionParticipantSchema,
    SyncPageSchema,
)
from .services import (
    ConversationSummary,
    MessageAccessDenied,
    MessageValidationError,
    RecipientDirectoryEntry,
    SessionMessageResult,
    SessionParticipantEntry,
    conversation_summary,
    create_message,
    get_authorized_conversation,
    get_or_create_conversation,
    get_owned_session,
    inbox_page,
    mark_conversation_read,
    message_cursor,
    message_page,
    recipient_directory_page,
    send_session_messages,
    session_participant_page,
    sync_page,
)

messages_router = Router(tags=["messages"])


def _not_found() -> NoReturn:
    raise Http404


def _validation_error(error: MessageValidationError) -> NoReturn:
    raise ValidationError(errors=[{"messages": str(error)}])


def _peer_schema(user: User) -> MessagePeerSchema:
    return MessagePeerSchema(
        slug=user.slug,
        name=user.name,
        profile_image=user.profile_image.url if user.profile_image else None,
        profile_avatar_seed=user.profile_avatar_seed,
        profile_avatar_type=ProfileAvatarTypeEnum(user.profile_avatar_type),
    )


def _message_schema(message: Message, user: User) -> MessageSchema:
    return MessageSchema(
        id=message.pk,
        sender_slug=message.sender.slug,
        text=message.body,
        client_message_id=message.client_message_id,
        created_at=message.created_at,
        cursor=message_cursor(message),
        is_mine=message.sender_id == user.pk,
    )


def _preview_schema(message: Message | None, user: User) -> MessagePreviewSchema | None:
    if message is None:
        return None
    return MessagePreviewSchema(
        id=message.pk,
        sender_slug=message.sender.slug,
        text=message.body,
        created_at=message.created_at,
        is_mine=message.sender_id == user.pk,
    )


def _summary_schema(summary: ConversationSummary, user: User) -> ConversationSummarySchema:
    return ConversationSummarySchema(
        id=summary.conversation.pk,
        peer=_peer_schema(summary.peer),
        last_message=_preview_schema(summary.last_message, user),
        unread_count=summary.unread_count,
        updated_at=summary.conversation.last_activity_at,
    )


def _keeper_recipient_schema(entry: RecipientDirectoryEntry) -> KeeperRecipientSchema:
    return KeeperRecipientSchema(
        profile=_peer_schema(entry.user),
        existing_conversation_id=entry.existing_conversation_id,
        can_start_direct=True,
    )


def _participant_recipient_schema(entry: RecipientDirectoryEntry) -> ParticipantRecipientSchema:
    session = entry.latest_session
    return ParticipantRecipientSchema(
        profile=_peer_schema(entry.user),
        existing_conversation_id=entry.existing_conversation_id,
        can_start_direct=True,
        session_slug=session.slug,
        session_title=session.session_title_or_title(),
        session_start=session.start,
    )


def _session_participant_schema(entry: SessionParticipantEntry) -> SessionParticipantSchema:
    return SessionParticipantSchema(
        profile=_peer_schema(entry.user),
        sessions_count=entry.sessions_count,
    )


def _session_message_result_schema(result: SessionMessageResult) -> SessionMessageResultSchema:
    recipients = [
        SessionMessageRecipientResultSchema(
            recipient_slug=recipient.recipient_slug,
            conversation_id=recipient.conversation_id,
            message_id=recipient.message_id,
        )
        for recipient in result.recipients
    ]
    return SessionMessageResultSchema(
        requested_count=result.requested_count,
        sent_count=len(recipients),
        recipients=recipients,
    )


@messages_router.get(
    "/conversations",
    response={200: ConversationPageSchema},
    url_name="messages_conversations",
)
def list_conversations(
    request: HttpRequest,
    cursor: str | None = None,
    limit: int = 20,
    query: str = "",
):
    """Conversation summaries, optionally filtered by peer name or latest message text."""
    user: User = request.user  # type: ignore
    try:
        summaries, next_cursor, unread_count = inbox_page(user, cursor=cursor, limit=limit, query=query)
    except MessageValidationError as error:
        _validation_error(error)
    return ConversationPageSchema(
        items=[_summary_schema(summary, user) for summary in summaries],
        next_cursor=next_cursor,
        total_unread_count=unread_count,
    )


@messages_router.post(
    "/conversations",
    response={201: ConversationSummarySchema},
    url_name="messages_conversation_open",
)
def open_conversation(request: HttpRequest, payload: OpenConversationSchema):
    user: User = request.user  # type: ignore
    peer = User.objects.filter(slug=payload.recipient_slug).first()
    if peer is None:
        _not_found()
    try:
        conversation = get_or_create_conversation(user, peer)
        return _summary_schema(conversation_summary(conversation, user), user)
    except MessageAccessDenied:
        _not_found()


@messages_router.get(
    "/conversations/{conversation_id}",
    response={200: ConversationSummarySchema},
    url_name="messages_conversation_detail",
)
def get_conversation(request: HttpRequest, conversation_id: UUID):
    user: User = request.user  # type: ignore
    try:
        conversation = get_authorized_conversation(conversation_id, user)
        return _summary_schema(conversation_summary(conversation, user), user)
    except MessageAccessDenied:
        _not_found()


@messages_router.get(
    "/recipients",
    response={200: RecipientDirectorySchema},
    url_name="messages_recipients",
)
def list_recipients(
    request: HttpRequest,
    kind: RecipientDirectoryKind | None = None,
    query: str = "",
    cursor: str | None = None,
    limit: int = 20,
):
    """Authorized 1:1 recipients; omit ``kind`` to prefer eligible keepers for dual-role users.

    The first ordered keepers page powers recommendations. Participants always
    receive their keepers directory; keepers composing to their own participants
    must explicitly request ``kind=participants``.
    """
    user: User = request.user  # type: ignore
    try:
        directory_kind, entries, next_cursor = recipient_directory_page(
            user,
            kind=kind.value if kind else None,
            query=query,
            cursor=cursor,
            limit=limit,
        )
    except MessageAccessDenied:
        _not_found()
    except MessageValidationError as error:
        _validation_error(error)
    keepers = [_keeper_recipient_schema(entry) for entry in entries] if directory_kind == "keepers" else []
    participants = (
        [_participant_recipient_schema(entry) for entry in entries] if directory_kind == "participants" else []
    )
    return RecipientDirectorySchema(
        kind=RecipientDirectoryKind(directory_kind),
        keepers=keepers,
        participants=participants,
        next_cursor=next_cursor,
    )


@messages_router.get(
    "/conversations/{conversation_id}/messages",
    response={200: MessagePageSchema},
    url_name="messages_history",
)
def list_messages(
    request: HttpRequest,
    conversation_id: UUID,
    before: str | None = None,
    after: str | None = None,
    limit: int = 30,
):
    user: User = request.user  # type: ignore
    try:
        conversation = get_authorized_conversation(conversation_id, user)
        messages, next_before, next_after, has_more = message_page(
            conversation,
            user,
            before=before,
            after=after,
            limit=limit,
        )
    except MessageAccessDenied:
        _not_found()
    except MessageValidationError as error:
        _validation_error(error)
    return MessagePageSchema(
        items=[_message_schema(message, user) for message in messages],
        next_before=next_before,
        next_after=next_after,
        has_more=has_more,
    )


@messages_router.post(
    "/conversations/{conversation_id}/messages",
    response={201: MessageSchema},
    url_name="messages_send",
)
def send_message(request: HttpRequest, conversation_id: UUID, payload: SendMessageSchema):
    user: User = request.user  # type: ignore
    try:
        conversation = get_authorized_conversation(conversation_id, user)
        message = create_message(conversation, user, payload.text, payload.client_message_id)
    except MessageAccessDenied:
        _not_found()
    except MessageValidationError as error:
        _validation_error(error)
    message.sender = user
    return Status(201, _message_schema(message, user))


@messages_router.post(
    "/conversations/{conversation_id}/read",
    response={204: None},
    url_name="messages_read",
)
def mark_read(request: HttpRequest, conversation_id: UUID, payload: MarkReadSchema):
    user: User = request.user  # type: ignore
    try:
        conversation = get_authorized_conversation(conversation_id, user)
        mark_conversation_read(conversation, user, payload.last_read_message_id)
    except MessageAccessDenied:
        _not_found()
    except MessageValidationError as error:
        _validation_error(error)
    return Status(204, None)


@messages_router.get("/sync", response={200: SyncPageSchema}, url_name="messages_sync")
def sync_messages(request: HttpRequest, since: str | None = None, limit: int = 50):
    user: User = request.user  # type: ignore
    try:
        summaries, removed_conversation_ids, next_cursor, unread_count = sync_page(user, since=since, limit=limit)
    except MessageValidationError as error:
        _validation_error(error)
    return SyncPageSchema(
        items=[_summary_schema(summary, user) for summary in summaries],
        removed_conversation_ids=removed_conversation_ids,
        next_cursor=next_cursor,
        total_unread_count=unread_count,
    )


@messages_router.get(
    "/sessions/{session_slug}/participants",
    response={200: SessionParticipantPageSchema},
    url_name="messages_session_participants",
)
def list_session_participants(
    request: HttpRequest,
    session_slug: str,
    cursor: str | None = None,
    limit: int = 20,
):
    user: User = request.user  # type: ignore
    try:
        session = get_owned_session(session_slug, user)
        entries, next_cursor = session_participant_page(session, user, cursor=cursor, limit=limit)
    except MessageAccessDenied:
        _not_found()
    except MessageValidationError as error:
        _validation_error(error)
    return SessionParticipantPageSchema(
        items=[_session_participant_schema(entry) for entry in entries],
        next_cursor=next_cursor,
    )


@messages_router.post(
    "/sessions/{session_slug}/messages",
    response={201: SessionMessageResultSchema},
    url_name="messages_session_send",
)
def send_session_message(request: HttpRequest, session_slug: str, payload: SendSessionMessagesSchema):
    user: User = request.user  # type: ignore
    try:
        session = get_owned_session(session_slug, user)
        result = send_session_messages(
            session,
            user,
            recipient_slugs=payload.recipient_slugs,
            text=payload.text,
            client_request_id=payload.client_request_id,
        )
    except MessageAccessDenied:
        _not_found()
    except MessageValidationError as error:
        _validation_error(error)
    return Status(201, _session_message_result_schema(result))
