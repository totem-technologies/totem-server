from django.contrib import admin

from .models import AutomationPrompt, Conversation, ConversationMembership, Message, MessageNotification


class ReadOnlyMessagingAdmin(admin.ModelAdmin):
    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return request.method in {"GET", "HEAD", "OPTIONS"} and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Conversation)
class ConversationAdmin(ReadOnlyMessagingAdmin):
    list_display = ("id", "user_low", "user_high", "last_activity_at")
    raw_id_fields = ("user_low", "user_high")
    readonly_fields = ("id", "user_low", "user_high", "created_at", "last_activity_at")


@admin.register(ConversationMembership)
class ConversationMembershipAdmin(ReadOnlyMessagingAdmin):
    list_display = ("id", "conversation", "user", "last_read_at", "updated_at")
    raw_id_fields = ("conversation", "user", "last_read_message")
    readonly_fields = (
        "id",
        "conversation",
        "user",
        "last_read_message",
        "last_read_at",
        "created_at",
        "updated_at",
    )


@admin.register(Message)
class MessageAdmin(ReadOnlyMessagingAdmin):
    list_display = ("id", "conversation", "sender", "created_at")
    raw_id_fields = ("conversation", "sender")
    readonly_fields = ("id", "conversation", "sender", "body", "client_message_id", "created_at")


@admin.register(MessageNotification)
class MessageNotificationAdmin(ReadOnlyMessagingAdmin):
    list_display = ("id", "message", "recipient", "status", "attempt_count", "last_attempt_at", "delivered_at")
    list_filter = ("status",)
    raw_id_fields = ("message", "recipient")
    readonly_fields = (
        "id",
        "message",
        "recipient",
        "status",
        "attempt_count",
        "created_at",
        "last_attempt_at",
        "claimed_at",
        "delivered_at",
    )


@admin.register(AutomationPrompt)
class AutomationPromptAdmin(ReadOnlyMessagingAdmin):
    list_display = ("id", "kind", "recipient", "session", "status", "created_at")
    list_filter = ("kind", "status")
    raw_id_fields = ("recipient", "session")
    readonly_fields = (
        "id",
        "idempotency_key",
        "recipient",
        "session",
        "kind",
        "status",
        "created_at",
        "delivered_at",
        "dismissed_at",
        "completed_at",
    )
