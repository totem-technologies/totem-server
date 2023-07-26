from django.contrib import admin

from .models import Circle


@admin.register(Circle)
class CircleAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "start", "published")
    filter_horizontal = ("attendees",)
    readonly_fields = ("attendee_list",)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["author"].initial = request.user
        form.base_fields["attendees"].initial = [request.user]
        return form
