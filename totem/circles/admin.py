from django.contrib import admin

from .models import Circle


@admin.register(Circle)
class CircleAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "start")
    filter_horizontal = ("attendees",)
