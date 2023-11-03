from django.contrib import admin
from django.utils import timezone

from .models import Circle, CircleEvent


class CircleEventInline(admin.StackedInline):
    model = CircleEvent
    extra = 0
    filter_horizontal = ["attendees"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        now_minus_1_hour = timezone.now() - timezone.timedelta(hours=1)
        return qs.filter(start__gte=now_minus_1_hour).order_by("start")


@admin.register(Circle)
class CircleAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "published")
    readonly_fields = ("subscribed_list",)
    filter_horizontal = ["subscribed"]
    inlines = [
        CircleEventInline,
    ]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["author"].initial = request.user
        form.base_fields["subscribed"].initial = [request.user]
        return form


@admin.register(CircleEvent)
class CircleEventAdmin(admin.ModelAdmin):
    list_display = ("start", "circle", "slug")
    list_filter = ["circle"]
    filter_horizontal = ["attendees", "joined"]
