from typing import Any

from django.contrib import admin
from django.utils import timezone

from .models import Circle, CircleCategory, CircleEvent


class DropdownFilter(admin.SimpleListFilter):
    template = "admin/dropdown_filter.html"
    parameter_name = "circle"
    title = "circle"

    def lookups(self, request, model_admin):
        return Circle.objects.values_list("slug", "title")

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(circle__slug=self.value())
        return queryset


@admin.register(CircleCategory)
class CircleCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)


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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        now_minus_2_hour = timezone.now() - timezone.timedelta(hours=2)
        return qs.filter(start__gte=now_minus_2_hour).order_by("start").prefetch_related("attendees", "joined")

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields["attendees"].initial = [request.user]
        return formset


@admin.register(Circle)
class CircleAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ("title", "slug", "published")
    readonly_fields = ("subscribed_list", "date_created", "date_modified")
    autocomplete_fields = ["subscribed", "categories"]
    inlines = [
        CircleEventInline,
    ]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["author"].initial = request.user
        form.base_fields["subscribed"].initial = [request.user]
        return form

    def save_formset(self, request: Any, form: Any, formset: Any, change: Any) -> None:
        if change:
            obj_list = formset.save(commit=False)
            for obj in obj_list:
                if isinstance(obj, CircleEvent):
                    obj.save_to_calendar()
        super().save_formset(request, form, formset, change)


@admin.register(CircleEvent)
class CircleEventAdmin(admin.ModelAdmin):
    list_display = ("start", "title", "circle", "slug")
    list_filter = ["start", DropdownFilter]
    autocomplete_fields = ["attendees", "joined"]
    readonly_fields = ("date_created", "date_modified")

    def save_model(self, request, obj: CircleEvent, form, change):
        obj.save_to_calendar()
        super().save_model(request, obj, form, change)
