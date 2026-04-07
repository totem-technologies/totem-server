import datetime
from typing import Any, final, override

from django.contrib import admin, messages
from django.db.models.query import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from totem.rooms.models import Room
from totem.rooms.schemas import RoomStatus
from totem.users.models import User
from totem.utils.admin import StaleDataCheckAdminMixin

from .models import Session, SessionFeedback, Space, SpaceCategory


@final
class SpaceDropdownFilter(admin.SimpleListFilter):
    template = "admin/dropdown_filter.html"
    parameter_name = "space"
    title = "space"

    @override
    def lookups(self, request, model_admin):
        return Space.objects.order_by("title").values_list("slug", "title")

    @override
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(space__slug=self.value())
        return queryset


@final
class AuthorDropdownFilter(admin.SimpleListFilter):
    template = "admin/dropdown_filter.html"
    parameter_name = "space__author"
    title = "author"

    @override
    def lookups(self, request, model_admin):
        return User.objects.filter(keeper_profile__isnull=False).values_list("slug", "name")

    @override
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(space__author__slug=self.value())
        return queryset


@final
@admin.register(SpaceCategory)
class SpaceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "description")


@final
class SessionInline(StaleDataCheckAdminMixin, admin.StackedInline):
    model = Session
    extra = 0
    autocomplete_fields = ["attendees", "joined"]
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "title",
                    "start",
                    "open",
                    "listed",
                    "cancelled",
                    "seats",
                    "attendees",
                    "joined",
                ]
            },
        ),
        ("Content", {"fields": ["content"], "classes": ["collapse"]}),
        (
            "Advanced",
            {
                "fields": ["meeting_url", "notified", "notified_missed", "notified_tomorrow", "advertised"],
                "classes": ["collapse"],
            },
        ),
    ]

    @override
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        now_minus_2_hour = timezone.now() - datetime.timedelta(hours=2)
        return qs.filter(start__gte=now_minus_2_hour).order_by("start").prefetch_related("attendees", "joined")

    @override
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields["attendees"].initial = [request.user]  # type: ignore
        return formset


@final
@admin.register(Space)
class SpaceAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ("title", "slug", "published")
    readonly_fields = ("subscribed_list", "date_created", "date_modified")
    autocomplete_fields = ["subscribed", "categories"]
    inlines = [
        SessionInline,
    ]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        form.base_fields["author"].initial = request.user  # type: ignore
        form.base_fields["subscribed"].initial = [request.user]  # type: ignore
        return form

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        if change:
            obj_list = formset.save(commit=False)
            for obj in obj_list:
                if isinstance(obj, Session):
                    obj.save_to_calendar()
        super().save_formset(request, form, formset, change)


def copy_session(modeladmin, request, queryset: QuerySet[Session]):
    if queryset.count() != 1:
        modeladmin.message_user(request, "Please select exactly one item to copy.", level=messages.ERROR)
        return
    session = queryset.first()
    if not session:
        return
    obj = Session.objects.create(
        title=session.title,
        open=False,
        listed=False,
        # start now
        start=timezone.now(),
        duration_minutes=session.duration_minutes,
        seats=session.seats,
        space=session.space,
        content=session.content,
    )
    change_url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])
    return redirect(change_url)


class SessionFeedbackInline(admin.TabularInline):
    model = SessionFeedback
    extra = 0
    readonly_fields = ("user", "feedback", "message", "date_created")


class RoomInline(admin.StackedInline):
    model = Room
    extra = 0
    max_num = 1
    can_delete = False
    fields = ("status", "room_turn_state", "end_reason", "room_state_version")
    readonly_fields = ("room_turn_state", "room_state_version")

    @admin.display(description="Turn State")
    def room_turn_state(self, obj: Room) -> str:
        return obj.turn_state

    @admin.display(description="State Version")
    def room_state_version(self, obj: Room) -> int:
        return obj.state_version

    def _format_choice_label(self, value: object, fallback_label: object) -> str:
        if isinstance(value, str) and value:
            return value.replace("_", " ").title()
        return str(fallback_label)

    @override
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        form_field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if form_field is None:
            return None
        if db_field.name == "status":
            form_field.label = "Room Status"
        if db_field.name == "end_reason":
            form_field.label = "End Reason"
        if db_field.name in {"status", "end_reason"}:
            form_field.choices = [
                (value, self._format_choice_label(value, label)) for value, label in form_field.choices
            ]
        return form_field


@final
@admin.register(Session)
class SessionAdmin(StaleDataCheckAdminMixin, admin.ModelAdmin):
    list_display = ("start", "title", "space", "slug")
    list_filter = [AuthorDropdownFilter, SpaceDropdownFilter, "start", "listed", "open", "cancelled"]
    autocomplete_fields = ["attendees", "joined"]
    readonly_fields = ("date_created", "date_modified")
    actions = [copy_session]
    inlines = [SessionFeedbackInline, RoomInline]

    @override
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "space":
            kwargs["queryset"] = Space.objects.order_by("title")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "space",
                    "title",
                    "start",
                    "duration_minutes",
                    "seats",
                    "content",
                    "attendees",
                    "joined",
                    "meeting_url",
                )
            },
        ),
        ("Visibility", {"fields": ("listed", "open", "cancelled")}),
        (
            "Automated Sent Notifications (Advanced)",
            {"fields": ("notified", "notified_missed", "notified_tomorrow", "advertised"), "classes": ("collapse",)},
        ),
    )

    def _sync_session_ended_at(self, session: Session) -> None:
        room = Room.objects.filter(session=session).first()
        if room is None:
            return
        if room.status == RoomStatus.ENDED and session.ended_at is None:
            session.ended_at = timezone.now()
            session.save(update_fields=["ended_at"])
            return
        if room.status != RoomStatus.ENDED and session.ended_at is not None:
            session.ended_at = None
            session.save(update_fields=["ended_at"])

    @override
    def save_model(self, request: HttpRequest, obj: Session, form: "ModelForm[Session]", change: bool):
        obj.save_to_calendar()
        super().save_model(request, obj, form, change)

    @override
    def save_related(self, request: HttpRequest, form: ModelForm, formsets: list[Any], change: bool) -> None:
        super().save_related(request, form, formsets, change)
        self._sync_session_ended_at(form.instance)
