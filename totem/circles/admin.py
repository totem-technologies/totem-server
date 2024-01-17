from typing import Any

from django.contrib import admin
from django.utils import timezone

from .models import Circle, CircleEvent


class CircleEventInline(admin.StackedInline):
    model = CircleEvent
    extra = 0
    autocomplete_fields = ["attendees", "joined"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        now_minus_1_hour = timezone.now() - timezone.timedelta(hours=1)
        return qs.filter(start__gte=now_minus_1_hour).order_by("start")


@admin.register(Circle)
class CircleAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ("title", "slug", "published")
    readonly_fields = ("subscribed_list",)
    autocomplete_fields = ["subscribed"]
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
    list_display = ("start", "circle", "slug")
    list_filter = ["circle"]
    autocomplete_fields = ["attendees", "joined"]

    def save_model(self, request, obj: CircleEvent, form, change):
        obj.save_to_calendar()
        super().save_model(request, obj, form, change)
