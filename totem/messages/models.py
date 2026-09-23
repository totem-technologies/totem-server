from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

if TYPE_CHECKING:
    from totem.users.models import User

MAX_MESSAGE_LENGTH = 4000
MAX_SESSION_MESSAGE_RECIPIENTS = 50


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_as_low_user",
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_as_high_user",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(default=timezone.now)
    last_message = models.ForeignKey(
        "Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="latest_for_conversations",
    )
    user_low_id: int
    last_message_id: uuid.UUID | None
    user_high_id: int
    memberships: models.Manager[ConversationMembership]
    messages: models.Manager[Message]

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(user_low_id__lt=F("user_high_id")), name="messaging_pair_canonical"),
            models.UniqueConstraint(fields=["user_low", "user_high"], name="messaging_user_pair_unique"),
        ]
        indexes = [models.Index(fields=["-last_activity_at", "-id"], name="messaging_inbox_order_idx")]

    def peer_for(self, user_id: int) -> User:
        if user_id == self.user_low_id:
            return self.user_high
        if user_id == self.user_high_id:
            return self.user_low
        raise ValueError("User is not a conversation member")


class MessagingSyncState(models.Model):
    """Singleton counter that orders membership changes for incremental sync."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    version = models.BigIntegerField(default=0)


class ConversationMembership(models.Model):
    class Slot(models.TextChoices):
        LOW = "low", "Low user"
        HIGH = "high", "High user"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="memberships")
    slot = models.CharField(max_length=4, choices=Slot.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="message_memberships")
    last_read_message = models.ForeignKey(
        "Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="read_by_memberships",
    )
    last_read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sync_version = models.BigIntegerField(default=0)
    unread_count = models.PositiveIntegerField(default=0)
    user_id: int
    last_read_message_id: uuid.UUID | None

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="messaging_conversation_member_unique"),
            models.UniqueConstraint(fields=["conversation", "slot"], name="messaging_conversation_slot_unique"),
        ]
        indexes = [
            models.Index(fields=["user", "sync_version", "id"], name="messaging_sync_lookup_idx"),
            models.Index(fields=["user", "conversation"], name="messaging_member_lookup_idx"),
        ]


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="direct_messages")
    body = models.CharField(max_length=MAX_MESSAGE_LENGTH)
    client_message_id = models.UUIDField(null=True, blank=True)
    bulk_request = models.ForeignKey(
        "SessionMessageRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_direct_messages",
    )
    conversation_id: uuid.UUID
    sender_id: int
    deleted_by_id: int | None
    bulk_request_id: uuid.UUID | None

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "client_message_id"],
                condition=Q(client_message_id__isnull=False),
                name="messaging_sender_client_message_unique",
            )
        ]
        indexes = [models.Index(fields=["conversation", "-created_at", "-id"], name="messaging_history_idx")]
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Messages are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Messages are immutable")


class MessageNotification(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        DELIVERED = "delivered", "Delivered"
        DISMISSED = "dismissed", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="notification")
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="message_notifications"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    message_id: uuid.UUID
    recipient_id: int

    class Meta:
        indexes = [
            models.Index(fields=["status", "last_attempt_at"], name="messaging_notify_retry_idx"),
            models.Index(fields=["recipient", "status"], name="messaging_notify_user_idx"),
        ]


class SessionMessageRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    keeper = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="session_message_requests"
    )
    session = models.ForeignKey("spaces.Session", on_delete=models.CASCADE, related_name="message_requests")
    client_request_id = models.UUIDField()
    body = models.CharField(max_length=MAX_MESSAGE_LENGTH)
    requested_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    keeper_id: int
    session_id: int
    messages: models.Manager[Message]

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["keeper", "client_request_id"], name="messaging_keeper_request_unique")
        ]


class AutomationPrompt(models.Model):
    class Kind(models.TextChoices):
        KEEPER_FOLLOW_UP = "keeper_follow_up", "Keeper follow-up"
        SHARE_UPCOMING_SPACE = "share_upcoming_space", "Share an upcoming space"
        PARTICIPANT_DISCOVERY = "participant_discovery", "Participant discovery"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        DISMISSED = "dismissed", "Dismissed"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=255, unique=True)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="automation_prompts")
    session = models.ForeignKey(
        "spaces.Session",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="message_automation_prompts",
    )
    kind = models.CharField(max_length=40, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["recipient", "status", "-created_at"], name="messaging_prompt_user_idx"),
            models.Index(fields=["session", "kind"], name="messaging_prompt_session_idx"),
        ]

    def mark_delivered(self) -> None:
        if self.status != self.Status.PENDING:
            return
        self.status = self.Status.DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=["status", "delivered_at"])

    def dismiss(self) -> None:
        if self.status == self.Status.COMPLETED:
            return
        self.status = self.Status.DISMISSED
        self.dismissed_at = timezone.now()
        self.save(update_fields=["status", "dismissed_at"])

    def complete(self) -> None:
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])
