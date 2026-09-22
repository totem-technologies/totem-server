import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from totem.notifications.services import send_notification_to_user
from totem.spaces.models import Session
from totem.users.models import User

from .models import (
    MAX_MESSAGE_LENGTH,
    Conversation,
    ConversationMembership,
    Message,
    MessageNotification,
    SessionMessageRequest,
)

logger = logging.getLogger(__name__)
_CURSOR_SALT = "totem.messages.cursor.v1"
MAX_SESSION_MESSAGE_RECIPIENTS = 50


class MessageAccessDenied(Exception):
    pass


class MessageValidationError(Exception):
    pass


@dataclass(frozen=True)
class ConversationSummary:
    conversation: Conversation
    membership: ConversationMembership
    peer: User
    last_message: Message | None
    unread_count: int


@dataclass(frozen=True)
class RecipientDirectoryEntry:
    user: User
    existing_conversation_id: UUID | None
    existing_conversation_created_at: datetime | None
    latest_session: Session
    session_titles: tuple[str, ...]


@dataclass(frozen=True)
class SessionParticipantEntry:
    user: User
    sessions_count: int


@dataclass(frozen=True)
class SessionMessageRecipientResult:
    recipient_slug: str
    conversation_id: UUID
    message_id: UUID


@dataclass(frozen=True)
class SessionMessageResult:
    requested_count: int
    recipients: list[SessionMessageRecipientResult]


def is_messaging_keeper(user: User) -> bool:
    """Keepers must hold the canonical KeeperProfile, not merely own a Space."""
    return user.is_active and user.is_keeper()


def qualifying_sessions(*, keeper: User, participant: User):
    """The single authoritative keeper/participant relationship query."""
    if not is_messaging_keeper(keeper) or keeper.pk == participant.pk or not participant.is_active:
        return Session.objects.none()
    participant_visible_ids = Session.objects.visible_to(participant).values("pk")
    return (
        Session.objects.visible_to(keeper)
        .filter(pk__in=participant_visible_ids, space__author=keeper)
        .filter(Q(attendees=participant) | Q(joined=participant))
        .exclude(room__banned_participants__contains=[participant.slug])
        .distinct()
    )


def session_allows_messaging(session: Session, keeper: User, participant: User) -> bool:
    return (
        session.space.author_id == keeper.pk
        and qualifying_sessions(keeper=keeper, participant=participant).filter(pk=session.pk).exists()
    )


def can_users_message(actor: User, peer: User) -> bool:
    """Return whether this exact pair currently has a valid private 1:1 relation."""
    if actor.pk == peer.pk or not actor.is_active or not peer.is_active:
        return False
    # The session's Space.author establishes the keeper role for this pair.
    # A KeeperProfile holder may still attend another keeper's session as a participant.
    return (
        qualifying_sessions(keeper=actor, participant=peer).exists()
        or qualifying_sessions(
            keeper=peer,
            participant=actor,
        ).exists()
    )


def require_users_can_message(actor: User, peer: User) -> None:
    if not can_users_message(actor, peer):
        raise MessageAccessDenied


def _ordered_users(first: User, second: User) -> tuple[User, User]:
    return (first, second) if first.pk < second.pk else (second, first)


def get_or_create_conversation(actor: User, peer: User) -> Conversation:
    require_users_can_message(actor, peer)
    low, high = _ordered_users(actor, peer)
    try:
        with transaction.atomic():
            conversation, created = Conversation.objects.get_or_create(user_low=low, user_high=high)
            if created:
                ConversationMembership.objects.bulk_create(
                    [
                        ConversationMembership(
                            conversation=conversation,
                            user=low,
                            slot=ConversationMembership.Slot.LOW,
                        ),
                        ConversationMembership(
                            conversation=conversation,
                            user=high,
                            slot=ConversationMembership.Slot.HIGH,
                        ),
                    ]
                )
            return conversation
    except IntegrityError:
        return Conversation.objects.get(user_low=low, user_high=high)


def require_conversation_access(conversation: Conversation, actor: User) -> User:
    try:
        peer = conversation.peer_for(actor.pk)
    except ValueError as error:
        raise MessageAccessDenied from error
    require_users_can_message(actor, peer)
    return peer


def get_authorized_conversation(conversation_id: UUID, actor: User) -> Conversation:
    try:
        conversation = Conversation.objects.select_related("user_low", "user_high").get(
            pk=conversation_id,
            memberships__user=actor,
        )
    except Conversation.DoesNotExist as error:
        raise MessageAccessDenied from error
    require_conversation_access(conversation, actor)
    return conversation


def _sign_cursor(value: dict[str, Any]) -> str:
    return signing.Signer(salt=_CURSOR_SALT).sign(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _unsign_cursor(cursor: str) -> dict[str, Any]:
    return json.loads(signing.Signer(salt=_CURSOR_SALT).unsign(cursor))


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


def _encode_cursor(
    created_at: datetime,
    object_id: UUID,
    *,
    kind: str,
    scope: str,
    query: str | None = None,
) -> str:
    value = {"at": created_at.isoformat(), "id": str(object_id), "kind": kind, "scope": scope}
    if query is not None:
        value["query"] = _query_hash(query)
    return _sign_cursor(value)


def _decode_cursor(
    cursor: str,
    *,
    kind: str,
    scope: str,
    query: str | None = None,
) -> tuple[datetime, UUID]:
    try:
        value = _unsign_cursor(cursor)
        if (
            value.get("kind") != kind
            or value.get("scope") != scope
            or (query is None and "query" in value)
            or (query is not None and value.get("query") != _query_hash(query))
        ):
            raise ValueError
        return datetime_from_iso(value["at"]), UUID(value["id"])
    except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
        raise MessageValidationError("Invalid cursor") from error


def datetime_from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        raise ValueError
    return parsed


def message_cursor(message: Message) -> str:
    return _encode_cursor(message.created_at, message.pk, kind="messages", scope=str(message.conversation_id))


def _message_has_been_read(notification: MessageNotification) -> bool:
    membership = (
        ConversationMembership.objects.select_related("last_read_message")
        .filter(
            conversation_id=notification.message.conversation_id,
            user_id=notification.recipient_id,
        )
        .first()
    )
    if membership is None or membership.last_read_message is None:
        return False
    last_read = membership.last_read_message
    return (notification.message.created_at, notification.message.pk) <= (last_read.created_at, last_read.pk)


def deliver_message_notification(notification_id: UUID) -> bool:
    """Attempt one direct-message FCM delivery without holding a database lock during I/O."""
    claimed_at = timezone.now()
    claimed = MessageNotification.objects.filter(
        pk=notification_id,
        status=MessageNotification.Status.PENDING,
    ).update(
        status=MessageNotification.Status.SENDING,
        claimed_at=claimed_at,
        last_attempt_at=claimed_at,
        attempt_count=F("attempt_count") + 1,
    )
    if not claimed:
        return False

    notification = MessageNotification.objects.select_related("message", "message__sender", "recipient").get(
        pk=notification_id
    )
    if _message_has_been_read(notification) or not can_users_message(
        notification.recipient, notification.message.sender
    ):
        MessageNotification.objects.filter(pk=notification_id, status=MessageNotification.Status.SENDING).update(
            status=MessageNotification.Status.DISMISSED,
            claimed_at=None,
        )
        return False

    try:
        delivered = send_notification_to_user(
            notification.recipient,
            title="New private message",
            body="Open Totem to read it.",
            data={
                "type": "message_received",
                "conversation_id": str(notification.message.conversation_id),
                "message_id": str(notification.message_id),
                "path": f"/messages/conversations/{notification.message.conversation_id}",
            },
        )
    except Exception:
        logger.exception("Failed to send direct-message notification for message %s", notification.message_id)
        delivered = False

    if delivered:
        MessageNotification.objects.filter(pk=notification_id, status=MessageNotification.Status.SENDING).update(
            status=MessageNotification.Status.DELIVERED,
            claimed_at=None,
            delivered_at=timezone.now(),
        )
    else:
        MessageNotification.objects.filter(pk=notification_id, status=MessageNotification.Status.SENDING).update(
            status=MessageNotification.Status.PENDING,
            claimed_at=None,
        )
    return delivered


def retry_unread_message_notifications() -> int:
    """Retry failed direct-message notifications at a bounded cadence until they are read."""
    retry_delay = timedelta(minutes=settings.MESSAGING_DIRECT_MESSAGE_RETRY_DELAY_MINUTES)
    retry_before = timezone.now() - retry_delay
    # A worker crash after claiming a row leaves it available for a later retry.
    MessageNotification.objects.filter(
        status=MessageNotification.Status.SENDING,
        claimed_at__lt=retry_before,
    ).update(status=MessageNotification.Status.PENDING, claimed_at=None)
    notification_ids = (
        MessageNotification.objects.filter(
            status=MessageNotification.Status.PENDING,
        )
        .filter(Q(last_attempt_at__isnull=True) | Q(last_attempt_at__lte=retry_before))
        .values_list("pk", flat=True)
    )
    return sum(deliver_message_notification(notification_id) for notification_id in notification_ids.iterator())


def _validated_message_body(text: str) -> str:
    body = text.strip()
    if not body:
        raise MessageValidationError("Message text cannot be empty")
    if len(body) > MAX_MESSAGE_LENGTH:
        raise MessageValidationError(f"Message text cannot exceed {MAX_MESSAGE_LENGTH} characters")
    return body


def create_message(
    conversation: Conversation,
    sender: User,
    text: str,
    client_message_id: UUID | str | None,
    *,
    bulk_request: SessionMessageRequest | None = None,
) -> Message:
    body = _validated_message_body(text)
    if client_message_id is not None and not isinstance(client_message_id, UUID):
        try:
            client_message_id = UUID(str(client_message_id))
        except (TypeError, ValueError) as error:
            raise MessageValidationError("Client message id must be a UUID") from error
    try:
        with transaction.atomic():
            locked_conversation = (
                Conversation.objects.select_for_update().select_related("user_low", "user_high").get(pk=conversation.pk)
            )
            recipient = require_conversation_access(locked_conversation, sender)
            if client_message_id is not None:
                existing = Message.objects.filter(sender=sender, client_message_id=client_message_id).first()
                if existing is not None:
                    if existing.conversation_id != locked_conversation.pk:
                        raise MessageValidationError("Client message id is already in use")
                    return existing
            message = Message.objects.create(
                conversation=locked_conversation,
                sender=sender,
                body=body,
                client_message_id=client_message_id,
                bulk_request=bulk_request,
            )
            Conversation.objects.filter(pk=locked_conversation.pk).update(
                last_activity_at=message.created_at,
                last_message=message,
            )
            ConversationMembership.objects.filter(conversation=locked_conversation).update(
                updated_at=message.created_at
            )
            ConversationMembership.objects.filter(conversation=locked_conversation, user=recipient).update(
                unread_count=F("unread_count") + 1,
                updated_at=message.created_at,
            )
            notification = MessageNotification.objects.create(message=message, recipient=recipient)
            transaction.on_commit(partial(deliver_message_notification, notification.pk))
            return message
    except IntegrityError:
        if client_message_id is None:
            raise
        message = Message.objects.get(sender=sender, client_message_id=client_message_id)
        if message.conversation_id != conversation.pk:
            raise MessageValidationError("Client message id is already in use")
        return message


def message_page(
    conversation: Conversation,
    actor: User,
    *,
    before: str | None,
    after: str | None = None,
    limit: int = 30,
) -> tuple[list[Message], str | None, str | None, bool]:
    require_conversation_access(conversation, actor)
    if before and after:
        raise MessageValidationError("Only one of before or after may be supplied")
    if limit < 1 or limit > 100:
        raise MessageValidationError("Limit must be between 1 and 100")
    messages = conversation.messages.select_related("sender")
    if after:
        after_at, after_id = _decode_cursor(after, kind="messages", scope=str(conversation.pk))
        page = list(
            messages.filter(Q(created_at__gt=after_at) | Q(created_at=after_at, id__gt=after_id)).order_by(
                "created_at", "id"
            )[: limit + 1]
        )
        has_more = len(page) > limit
        page = page[:limit]
        next_after = message_cursor(page[-1]) if page else after
        return page, None, next_after, has_more

    messages = messages.order_by("-created_at", "-id")
    if before:
        before_at, before_id = _decode_cursor(before, kind="messages", scope=str(conversation.pk))
        messages = messages.filter(Q(created_at__lt=before_at) | Q(created_at=before_at, id__lt=before_id))
    page = list(messages[: limit + 1])
    has_more = len(page) > limit
    page = page[:limit]
    next_before = message_cursor(page[-1]) if has_more else None
    next_after = message_cursor(page[0]) if page else None
    return page, next_before, next_after, has_more


def mark_conversation_read(
    conversation: Conversation,
    actor: User,
    last_read_message_id: UUID,
) -> ConversationMembership:
    with transaction.atomic():
        locked_conversation = (
            Conversation.objects.select_for_update().select_related("user_low", "user_high").get(pk=conversation.pk)
        )
        require_conversation_access(locked_conversation, actor)
        try:
            target = Message.objects.get(pk=last_read_message_id, conversation=locked_conversation)
        except Message.DoesNotExist as error:
            raise MessageValidationError("Message is not in this conversation") from error
        membership = ConversationMembership.objects.select_for_update().get(
            conversation=locked_conversation,
            user=actor,
        )
        current = membership.last_read_message
        target_position = (target.created_at, target.pk)
        current_position = (current.created_at, current.pk) if current is not None else None
        if current_position is None or target_position > current_position:
            membership.last_read_message = target
            membership.last_read_at = target.created_at
            membership.unread_count = 0
            membership.save(update_fields=["last_read_message", "last_read_at", "unread_count", "updated_at"])
            MessageNotification.objects.filter(
                recipient=actor,
                status=MessageNotification.Status.PENDING,
                message__conversation=locked_conversation,
            ).filter(
                Q(message__created_at__lt=target.created_at)
                | Q(message__created_at=target.created_at, message_id__lte=target.pk)
            ).update(status=MessageNotification.Status.DISMISSED)
        return membership


def _summary(membership: ConversationMembership) -> ConversationSummary:
    conversation = membership.conversation
    return ConversationSummary(
        conversation=conversation,
        membership=membership,
        peer=conversation.peer_for(membership.user_id),
        last_message=conversation.last_message,
        unread_count=membership.unread_count,
    )


def conversation_summary(conversation: Conversation, user: User) -> ConversationSummary:
    require_conversation_access(conversation, user)
    membership = ConversationMembership.objects.select_related(
        "conversation",
        "conversation__user_low",
        "conversation__user_low__keeper_profile",
        "conversation__user_high",
        "conversation__user_high__keeper_profile",
        "conversation__last_message",
        "conversation__last_message__sender",
    ).get(conversation=conversation, user=user)
    return _summary(membership)


def _directory_kind(user: User, requested_kind: str | None) -> str:
    if requested_kind is None:
        return _default_directory_kind(user)
    if requested_kind not in {"keepers", "participants"}:
        raise MessageValidationError("Invalid recipient directory kind")
    if requested_kind == "participants" and not is_messaging_keeper(user):
        return "keepers"
    return requested_kind


def _directory_candidates(user: User, kind: str):
    if kind == "participants":
        return (
            User.objects.filter(
                Q(sessions_attending__space__author=user) | Q(sessions_joined__space__author=user),
                is_active=True,
            )
            .exclude(pk=user.pk)
            .select_related("keeper_profile")
            .distinct()
        )
    return (
        User.objects.filter(
            Q(created_spaces__sessions__attendees=user) | Q(created_spaces__sessions__joined=user),
            is_active=True,
            keeper_profile__isnull=False,
        )
        .exclude(pk=user.pk)
        .select_related("keeper_profile")
        .distinct()
    )


def _default_directory_kind(user: User) -> str:
    if not is_messaging_keeper(user):
        return "keepers"
    if any(can_users_message(user, candidate) for candidate in _directory_candidates(user, "keepers").iterator()):
        return "keepers"
    return "participants"


def _existing_conversations(user: User, peer_ids: list[int]) -> dict[int, tuple[UUID, datetime]]:
    conversations = Conversation.objects.filter(
        Q(user_low=user, user_high_id__in=peer_ids) | Q(user_high=user, user_low_id__in=peer_ids)
    )
    return {
        conversation.user_high_id if conversation.user_low_id == user.pk else conversation.user_low_id: (
            conversation.pk,
            conversation.created_at,
        )
        for conversation in conversations
    }


def _directory_sort_key(kind: str, entry: RecipientDirectoryEntry, snapshot: datetime) -> tuple[int, float, int]:
    exists_at_snapshot = (
        entry.existing_conversation_created_at is not None and entry.existing_conversation_created_at <= snapshot
    )
    existing_rank = int(exists_at_snapshot) if kind == "keepers" else 0
    return existing_rank, -entry.latest_session.start.timestamp(), entry.user.pk


def _encode_directory_cursor(
    user: User,
    kind: str,
    query: str,
    entry: RecipientDirectoryEntry,
    snapshot: datetime,
) -> str:
    rank, _negative_timestamp, peer_id = _directory_sort_key(kind, entry, snapshot)
    return _sign_cursor(
        {
            "kind": kind,
            "scope": str(user.pk),
            "query": _query_hash(query),
            "rank": rank,
            "at": entry.latest_session.start.isoformat(),
            "peer": peer_id,
            "snapshot": snapshot.isoformat(),
        }
    )


def _decode_directory_cursor(user: User, kind: str, query: str, cursor: str) -> tuple[tuple[int, float, int], datetime]:
    try:
        value = _unsign_cursor(cursor)
        if value.get("kind") != kind or value.get("scope") != str(user.pk) or value.get("query") != _query_hash(query):
            raise ValueError
        relationship_at = datetime_from_iso(value["at"])
        snapshot = datetime_from_iso(value["snapshot"])
        return (int(value["rank"]), -relationship_at.timestamp(), int(value["peer"])), snapshot
    except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
        raise MessageValidationError("Invalid cursor") from error


def recipient_directory_page(
    user: User,
    *,
    kind: str | None,
    query: str,
    cursor: str | None,
    limit: int,
) -> tuple[str, list[RecipientDirectoryEntry], str | None]:
    if limit < 1 or limit > 50:
        raise MessageValidationError("Limit must be between 1 and 50")
    if len(query) > 100:
        raise MessageValidationError("Query cannot exceed 100 characters")
    normalized_query = query.strip().casefold()
    directory_kind = _directory_kind(user, kind)
    cursor_key: tuple[int, float, int] | None = None
    snapshot = timezone.now()
    if cursor:
        cursor_key, snapshot = _decode_directory_cursor(user, directory_kind, normalized_query, cursor)

    authorized: list[tuple[User, Session, tuple[str, ...]]] = []
    for candidate in _directory_candidates(user, directory_kind):
        keeper, participant = (user, candidate) if directory_kind == "participants" else (candidate, user)
        if not can_users_message(user, candidate):
            continue
        sessions = list(
            qualifying_sessions(keeper=keeper, participant=participant)
            .select_related("space")
            .order_by("-start", "-pk")
        )
        if not sessions:
            continue
        titles = tuple(session.session_title_or_title() for session in sessions)
        if (
            normalized_query
            and normalized_query not in candidate.name.casefold()
            and not any(normalized_query in title.casefold() for title in titles)
        ):
            continue
        authorized.append((candidate, sessions[0], titles))

    existing = _existing_conversations(user, [candidate.pk for candidate, _session, _titles in authorized])
    entries = [
        RecipientDirectoryEntry(
            user=candidate,
            existing_conversation_id=existing.get(candidate.pk, (None, None))[0],
            existing_conversation_created_at=existing.get(candidate.pk, (None, None))[1],
            latest_session=latest_session,
            session_titles=titles,
        )
        for candidate, latest_session, titles in authorized
    ]
    entries.sort(key=lambda entry: _directory_sort_key(directory_kind, entry, snapshot))
    if cursor_key:
        entries = [entry for entry in entries if _directory_sort_key(directory_kind, entry, snapshot) > cursor_key]
    page = entries[: limit + 1]
    has_more = len(page) > limit
    page = page[:limit]
    next_cursor = (
        _encode_directory_cursor(user, directory_kind, normalized_query, page[-1], snapshot) if has_more else None
    )
    return directory_kind, page, next_cursor


def _membership_queryset(user: User):
    return ConversationMembership.objects.filter(user=user).select_related(
        "conversation",
        "conversation__user_low",
        "conversation__user_high",
        "conversation__last_message",
        "conversation__last_message__sender",
    )


def inbox_page(
    user: User,
    *,
    cursor: str | None,
    limit: int,
    query: str = "",
) -> tuple[list[ConversationSummary], str | None, int]:
    if limit < 1 or limit > 50:
        raise MessageValidationError("Limit must be between 1 and 50")
    if len(query) > 100:
        raise MessageValidationError("Query cannot exceed 100 characters")
    normalized_query = query.strip().casefold()
    cursor_query = normalized_query or None
    memberships = _membership_queryset(user)
    if normalized_query:
        # NOTE: Search only the indexed inbox relation and latest preview; add
        # a dedicated, permission-scoped message-search index before searching history.
        memberships = memberships.filter(
            Q(conversation__user_low_id=user.pk, conversation__user_high__name__icontains=normalized_query)
            | Q(conversation__user_high_id=user.pk, conversation__user_low__name__icontains=normalized_query)
            | Q(conversation__last_message__body__icontains=normalized_query)
        )
    if cursor:
        cursor_at, cursor_id = _decode_cursor(
            cursor,
            kind="inbox",
            scope=str(user.pk),
            query=cursor_query,
        )
        memberships = memberships.filter(
            Q(conversation__last_activity_at__lt=cursor_at)
            | Q(conversation__last_activity_at=cursor_at, conversation_id__lt=cursor_id)
        )
    memberships = memberships.order_by("-conversation__last_activity_at", "-conversation_id")
    authorized: list[ConversationSummary] = []
    for membership in memberships.iterator(chunk_size=limit + 1):
        if can_users_message(user, membership.conversation.peer_for(user.pk)):
            authorized.append(_summary(membership))
            if len(authorized) > limit:
                break
    has_more = len(authorized) > limit
    authorized = authorized[:limit]
    next_cursor = None
    if has_more:
        last = authorized[-1].conversation
        next_cursor = _encode_cursor(
            last.last_activity_at,
            last.pk,
            kind="inbox",
            scope=str(user.pk),
            query=cursor_query,
        )
    return authorized, next_cursor, total_unread_count(user)


def total_unread_count(user: User) -> int:
    return ConversationMembership.objects.filter(user=user).aggregate(total=Sum("unread_count"))["total"] or 0


def sync_page(user: User, *, since: str | None, limit: int) -> tuple[list[ConversationSummary], str | None, int]:
    if limit < 1 or limit > 100:
        raise MessageValidationError("Limit must be between 1 and 100")
    memberships = _membership_queryset(user)
    if since:
        cursor_at, cursor_id = _decode_cursor(since, kind="sync", scope=str(user.pk))
        memberships = memberships.filter(Q(updated_at__gt=cursor_at) | Q(updated_at=cursor_at, id__gt=cursor_id))
    memberships = memberships.order_by("updated_at", "id")
    authorized: list[ConversationSummary] = []
    authorized_memberships: list[ConversationMembership] = []
    for membership in memberships.iterator(chunk_size=limit):
        if can_users_message(user, membership.conversation.peer_for(user.pk)):
            authorized.append(_summary(membership))
            authorized_memberships.append(membership)
            if len(authorized) >= limit:
                break
    next_cursor = None
    if authorized_memberships:
        last = authorized_memberships[-1]
        next_cursor = _encode_cursor(last.updated_at, last.pk, kind="sync", scope=str(user.pk))
    return authorized, next_cursor, total_unread_count(user)


def _session_participant_cursor_scope(user: User, session: Session) -> str:
    return f"{user.pk}:{session.pk}"


def _encode_session_participant_cursor(user: User, session: Session, entry: SessionParticipantEntry) -> str:
    return _sign_cursor(
        {
            "scope": _session_participant_cursor_scope(user, session),
            "name": entry.user.name.casefold(),
            "id": entry.user.pk,
        }
    )


def _decode_session_participant_cursor(user: User, session: Session, cursor: str) -> tuple[str, int]:
    try:
        value = _unsign_cursor(cursor)
        if value.get("scope") != _session_participant_cursor_scope(user, session):
            raise ValueError
        return str(value["name"]), int(value["id"])
    except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
        raise MessageValidationError("Invalid cursor") from error


def get_owned_session(session_slug: str, keeper: User) -> Session:
    if not is_messaging_keeper(keeper):
        raise MessageAccessDenied
    try:
        return (
            Session.objects.visible_to(keeper)
            .select_related("space", "space__author", "room")
            .get(
                slug=session_slug,
                space__author=keeper,
            )
        )
    except Session.DoesNotExist as error:
        raise MessageAccessDenied from error


def _session_messageable_participants(session: Session, keeper: User):
    return (
        User.objects.filter(Q(sessions_attending=session) | Q(sessions_joined=session), is_active=True)
        .exclude(pk=keeper.pk)
        .exclude(slug__in=session.banned_slugs())
        .annotate(message_sessions_count=Count("sessions_joined", distinct=True))
        .distinct()
    )


def session_participant_page(
    session: Session,
    keeper: User,
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[SessionParticipantEntry], str | None]:
    if limit < 1 or limit > 50:
        raise MessageValidationError("Limit must be between 1 and 50")
    entries = [
        SessionParticipantEntry(user=participant, sessions_count=participant.message_sessions_count)
        for participant in _session_messageable_participants(session, keeper)
        if session_allows_messaging(session, keeper, participant)
    ]
    entries.sort(key=lambda entry: (entry.user.name.casefold(), entry.user.pk))
    if cursor:
        name, user_id = _decode_session_participant_cursor(keeper, session, cursor)
        entries = [entry for entry in entries if (entry.user.name.casefold(), entry.user.pk) > (name, user_id)]
    page = entries[: limit + 1]
    has_more = len(page) > limit
    page = page[:limit]
    next_cursor = _encode_session_participant_cursor(keeper, session, page[-1]) if has_more else None
    return page, next_cursor


def _bulk_results(request: SessionMessageRequest, recipient_slugs: list[str]) -> SessionMessageResult:
    messages = request.messages.select_related("conversation__user_low", "conversation__user_high").all()
    by_slug: dict[str, Message] = {}
    for message in messages:
        peer = message.conversation.peer_for(request.keeper_id)
        by_slug[peer.slug] = message
    if set(by_slug) != set(recipient_slugs):
        raise MessageValidationError("Client request id is already in use")
    return SessionMessageResult(
        requested_count=request.requested_count,
        recipients=[
            SessionMessageRecipientResult(
                recipient_slug=slug,
                conversation_id=by_slug[slug].conversation_id,
                message_id=by_slug[slug].pk,
            )
            for slug in recipient_slugs
        ],
    )


def send_session_messages(
    session: Session,
    keeper: User,
    *,
    recipient_slugs: list[str],
    text: str,
    client_request_id: UUID,
) -> SessionMessageResult:
    body = _validated_message_body(text)
    if (
        not recipient_slugs
        or len(recipient_slugs) > MAX_SESSION_MESSAGE_RECIPIENTS
        or len(recipient_slugs) != len(set(recipient_slugs))
    ):
        raise MessageValidationError("Choose one or more distinct eligible participants")
    eligible = {user.slug: user for user in _session_messageable_participants(session, keeper)}
    recipients = [eligible.get(slug) for slug in recipient_slugs]
    if any(
        participant is None or not session_allows_messaging(session, keeper, participant) for participant in recipients
    ):
        raise MessageValidationError("Selected recipients are not eligible")

    try:
        with transaction.atomic():
            existing = SessionMessageRequest.objects.filter(keeper=keeper, client_request_id=client_request_id).first()
            if existing is not None:
                if existing.session_id != session.pk or existing.body != body:
                    raise MessageValidationError("Client request id is already in use")
                return _bulk_results(existing, recipient_slugs)
            request = SessionMessageRequest.objects.create(
                keeper=keeper,
                session=session,
                client_request_id=client_request_id,
                body=body,
                requested_count=len(recipient_slugs),
            )
            results: list[SessionMessageRecipientResult] = []
            for recipient in recipients:
                assert recipient is not None
                conversation = get_or_create_conversation(keeper, recipient)
                message = create_message(conversation, keeper, body, None, bulk_request=request)
                results.append(
                    SessionMessageRecipientResult(
                        recipient_slug=recipient.slug,
                        conversation_id=conversation.pk,
                        message_id=message.pk,
                    )
                )
            return SessionMessageResult(requested_count=len(results), recipients=results)
    except IntegrityError:
        request = SessionMessageRequest.objects.get(keeper=keeper, client_request_id=client_request_id)
        if request.session_id != session.pk or request.body != body:
            raise MessageValidationError("Client request id is already in use")
        return _bulk_results(request, recipient_slugs)
