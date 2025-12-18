import datetime
from typing import Any, final, override

from django.contrib import admin, messages
from django.db.models.query import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from totem.users.models import User

from .models import Circle, CircleCategory, CircleEvent, SessionFeedback


@final
class SpaceDropdownFilter(admin.SimpleListFilter):
    template = "admin/dropdown_filter.html"
    parameter_name = "circle"
    title = "circle"

    @override
    def lookups(self, request, model_admin):
        return Circle.objects.values_list("slug", "title")

    @override
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(circle__slug=self.value())
        return queryset


@final
class AuthorDropdownFilter(admin.SimpleListFilter):
    template = "admin/dropdown_filter.html"
    parameter_name = "circle__author"
    title = "author"

    @override
    def lookups(self, request, model_admin):
        return User.objects.filter(keeper_profile__isnull=False).values_list("slug", "name")

    @override
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(circle__author__slug=self.value())
        return queryset


@final
@admin.register(CircleCategory)
class CircleCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "description")


@final
class CircleEventInline(admin.StackedInline):
    model = CircleEvent
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
@admin.register(Circle)
class CircleAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ("title", "slug", "published")
    readonly_fields = ("subscribed_list", "date_created", "date_modified")
    autocomplete_fields = ["subscribed", "categories"]
    inlines = [
        CircleEventInline,
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
                if isinstance(obj, CircleEvent):
                    obj.save_to_calendar()
        super().save_formset(request, form, formset, change)


def copy_event(modeladmin, request, queryset: QuerySet[CircleEvent]):
    if queryset.count() != 1:
        modeladmin.message_user(request, "Please select exactly one item to copy.", level=messages.ERROR)
        return
    event = queryset.first()
    if not event:
        return
    obj = CircleEvent.objects.create(
        title=event.title,
        open=False,
        listed=False,
        # start now
        start=timezone.now(),
        duration_minutes=event.duration_minutes,
        seats=event.seats,
        circle=event.circle,
        content=event.content,
    )
    change_url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])
    return redirect(change_url)


class SessionFeedbackInline(admin.TabularInline):
    model = SessionFeedback
    extra = 0
    readonly_fields = ("user", "feedback", "message", "date_created")


@final
@admin.register(CircleEvent)
class CircleEventAdmin(admin.ModelAdmin):
    list_display = ("start", "title", "circle", "slug")
    list_filter = [AuthorDropdownFilter, SpaceDropdownFilter, "start", "listed", "open", "cancelled"]
    autocomplete_fields = ["attendees", "joined"]
    readonly_fields = ("date_created", "date_modified")
    actions = [copy_event]
    inlines = [SessionFeedbackInline]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "circle",
                    "title",
                    "start",
                    "duration_minutes",
                    "seats",
                    "content",
                    "attendees",
                    "joined",
                    "meeting_provider",
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

    @override
    def save_model(self, request: HttpRequest, obj: CircleEvent, form: "ModelForm[CircleEvent]", change: bool):
        obj.save_to_calendar()
        super().save_model(request, obj, form, change)
