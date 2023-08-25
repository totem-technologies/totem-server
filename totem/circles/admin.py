from django.contrib import admin

from .models import Circle, CircleEvent


class CircleEventInline(admin.StackedInline):
    model = CircleEvent
    extra = 0


@admin.register(Circle)
class CircleAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "published")
    readonly_fields = ("subscribed_list",)

    inlines = [
        CircleEventInline,
    ]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["author"].initial = request.user
        form.base_fields["subscribed"].initial = [request.user]
        return form
