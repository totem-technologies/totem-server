import uuid
from datetime import UTC, datetime
from typing import Optional

from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.pagination import CursorPagination, paginate

from totem.notifications.utils import notify_users
from totem.users.models import User

from .models import ChatMessage, ChatParticipant, ChatRoom
from .schemas import (
    KeeperBulkMessageInSchema,
    MessageOutSchema,
    SendMessageInSchema,
    ThreadOutSchema,
)

router = Router(tags=["Chat"])


def _message_to_schema(message: ChatMessage) -> MessageOutSchema:
    return MessageOutSchema(
        id=message.id,
        room_id=message.room_id,
        sender_id=message.sender_id,
        sender_name=message.sender.name or message.sender.email,
        content=message.content,
        created_at=message.created_at,
        client_id=message.client_id,
        session_id=message.session_id,
    )


def _count_unread(room: ChatRoom, user: User, last_read_at: datetime) -> int:
    return (
        ChatMessage.objects.filter(
            room=room,
            created_at__gt=last_read_at,
        )
        .exclude(sender=user)
        .count()
    )


@router.get("/threads", response=list[ThreadOutSchema], url_name="chat_list_threads")
def list_threads(request: HttpRequest) -> list[ThreadOutSchema]:
    """
    Lists the active conversation rooms for the authenticated user,
    complete with unread badge metrics and the latest thread message.
    """
    user: User = request.auth  # type: ignore
    memberships = ChatParticipant.objects.filter(user=user).select_related("room")

    threads: list[ThreadOutSchema] = []
    for member in memberships:
        room = member.room

        unread_cnt = _count_unread(room, user, member.last_read_at)

        last_msg = ChatMessage.objects.filter(room=room).select_related("sender").order_by("-created_at").first()

        last_msg_schema: Optional[MessageOutSchema] = None
        if last_msg:
            last_msg_schema = _message_to_schema(last_msg)

        threads.append(
            ThreadOutSchema(
                id=room.id,
                room_type=room.room_type,
                session_id=room.session_id,
                unread_count=unread_cnt,
                last_message=last_msg_schema,
            )
        )

    return threads


@router.get(
    "/threads/{thread_id}/messages",
    response=list[MessageOutSchema],
    url_name="chat_get_messages",
)
@paginate(CursorPagination, ordering=("-created_at",), page_size=50)
def get_thread_messages(request: HttpRequest, thread_id: uuid.UUID):
    """
    Retrieves messages inside a conversation thread. Optimized natively via
    CursorPagination to support stable dynamic scrolling on active threads.
    """
    user: User = request.auth  # type: ignore
    # Validate user is in room
    get_object_or_404(ChatParticipant, room_id=thread_id, user=user)

    # Update read receipt for the thread
    ChatParticipant.objects.filter(room_id=thread_id, user=user).update(last_read_at=datetime.now(UTC))

    return ChatMessage.objects.filter(room_id=thread_id).select_related("sender")


@router.post(
    "/threads/{thread_id}/messages",
    response={200: MessageOutSchema},
    url_name="chat_send_message",
)
def send_message(request: HttpRequest, thread_id: uuid.UUID, payload: SendMessageInSchema) -> MessageOutSchema:
    """
    Sends a message to a thread. Utilizes client_id to prevent redundant duplicates.
    """
    user: User = request.auth  # type: ignore
    participant = get_object_or_404(ChatParticipant, room_id=thread_id, user=user)

    # Check if client_id already exists to handle instant retries gracefully
    existing_message = ChatMessage.objects.filter(client_id=payload.client_id).first()
    if existing_message:
        return _message_to_schema(existing_message)

    with transaction.atomic():
        message = ChatMessage.objects.create(
            room_id=thread_id,
            sender=user,
            content=payload.content,
            client_id=payload.client_id,
            session_id=payload.session_id,
        )

        # Mark sending participant's read receipt instantly
        participant.last_read_at = message.created_at
        participant.save(update_fields=["last_read_at"])

    # Update room activity timestamp in cache
    _update_thread_activity(thread_id)

    # Dispatch notifications (best-effort, outside transaction)
    _dispatch_chat_notifications(message)

    return _message_to_schema(message)


@router.post(
    "/keeper/session-message",
    response={200: list[MessageOutSchema]},
    url_name="chat_keeper_bulk",
)
def keeper_bulk_message(request: HttpRequest, payload: KeeperBulkMessageInSchema) -> list[MessageOutSchema]:
    """
    Allows a Session Keeper to bulk-message specified participants.
    Groups them into individual direct message channels,
    and assigns the designated Session context to each message.
    """
    keeper: User = request.auth  # type: ignore
    created_messages: list[ChatMessage] = []

    with transaction.atomic():
        for target_user_id in payload.user_ids:
            target_user = get_object_or_404(User, id=target_user_id)

            # Locate or create the exact 1-to-1 Room containing the keeper and target user
            shared_rooms = ChatRoom.objects.filter(
                room_type=ChatRoom.RoomType.DIRECT,
                participants__user=keeper,
            ).filter(participants__user=target_user)

            if shared_rooms.exists():
                room = shared_rooms.first()
            else:
                room = ChatRoom.objects.create(
                    room_type=ChatRoom.RoomType.DIRECT,
                    session_id=payload.session_id,
                )
                ChatParticipant.objects.create(room=room, user=keeper)
                ChatParticipant.objects.create(room=room, user=target_user)

            # Write Message
            message = ChatMessage.objects.create(
                room=room,
                sender=keeper,
                content=payload.content,
                session_id=payload.session_id,
                client_id=uuid.uuid4(),  # Auto-generated backend-side for bulk outputs
            )

            created_messages.append(message)

    # Dispatch notifications for all generated messages
    for msg in created_messages:
        _update_thread_activity(msg.room_id)
        _dispatch_chat_notifications(msg)

    return [_message_to_schema(msg) for msg in created_messages]


@router.get(
    "/threads/{thread_id}/check-updates",
    url_name="chat_check_updates",
)
def check_updates(request: HttpRequest, thread_id: uuid.UUID, client_last_time: float):
    """
    Lightweight endpoint to check if a thread has new messages since a given timestamp.
    Uses Redis cache to avoid unnecessary DB queries.
    """
    user: User = request.auth  # type: ignore
    # Validate user is in room
    get_object_or_404(ChatParticipant, room_id=thread_id, user=user)

    last_activity = cache.get(f"chat:room:{thread_id}:last_activity")
    if last_activity and last_activity <= client_last_time:
        return {"has_updates": False}
    return {"has_updates": True}


# --- Helpers ---


def _update_thread_activity(room_id: uuid.UUID) -> None:
    """Save the current timestamp as the latest activity for a room in Redis."""
    cache.set(
        f"chat:room:{room_id}:last_activity",
        datetime.now(UTC).timestamp(),
        timeout=604800,  # 7 days
    )


def _dispatch_chat_notifications(message: ChatMessage) -> None:
    """Send push notifications to other participants in the room."""
    sender_display = message.sender.name or message.sender.email
    notification_title = f"New message from {sender_display}"
    notification_body = message.content[:150] + ("..." if len(message.content) > 150 else "")

    data = {
        "type": "chat_message",
        "thread_id": str(message.room_id),
        "message_id": str(message.id),
    }
    if message.session_id:
        data["session_id"] = str(message.session_id)

    recipients = list(
        ChatParticipant.objects.filter(room=message.room).exclude(user=message.sender).select_related("user")
    )
    users_to_notify = [r.user for r in recipients]
    if users_to_notify:
        notify_users(users_to_notify, notification_title, notification_body, data)
