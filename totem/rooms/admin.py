from typing import final, override

from django.contrib import admin
from django.utils.html import format_html

from totem.rooms.models import Room, RoomEventLog
from totem.rooms.schemas import RoomStatus
from totem.utils.admin import StaleDataCheckAdminMixin


class RoomEventLogInline(admin.TabularInline):
    model = RoomEventLog
    extra = 0
    can_delete = False
    readonly_fields = ("version", "event_type", "actor", "snapshot")

    @override
    def has_add_permission(self, request, obj=None):
        return False


@final
@admin.register(Room)
class RoomAdmin(StaleDataCheckAdminMixin, admin.ModelAdmin):
    list_display = ("session", "status", "turn_state", "state_version")
    list_filter = ("status",)
    readonly_fields = ("session_link", "turn_state", "state_version", "keeper", "current_speaker", "next_speaker", "talking_order", "banned_participants", "round_number", "round_message")
    inlines = [RoomEventLogInline]

    fieldsets = (
        (None, {"fields": ("session_link", "status", "end_reason")}),
        ("State", {"fields": ("turn_state", "state_version", "keeper", "current_speaker", "next_speaker", "round_number", "round_message")}),
        ("Participants", {"fields": ("talking_order", "banned_participants")}),
    )

    def _format_choice_label(self, value: object, fallback_label: object) -> str:
        if isinstance(value, str) and value:
            return value.replace("_", " ").title()
        return str(fallback_label)

    @override
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        form_field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if form_field is None:
            return None
        if db_field.name in {"status", "end_reason"}:
            form_field.choices = [
                (value, self._format_choice_label(value, label)) for value, label in form_field.choices
            ]
        return form_field

    @admin.display(description="Session")
    def session_link(self, obj: Room) -> str:
        from django.urls import reverse

        url = reverse("admin:spaces_session_change", args=[obj.session_id])
        return format_html('<a href="{}">{}</a>', url, obj.session)

    @override
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Sync session.ended_at when room status changes
        session = obj.session
        if obj.status == RoomStatus.ENDED and session.ended_at is None:
            from django.utils import timezone

            session.ended_at = timezone.now()
            session.save(update_fields=["ended_at"])
        elif obj.status != RoomStatus.ENDED and session.ended_at is not None:
            session.ended_at = None
            session.save(update_fields=["ended_at"])
