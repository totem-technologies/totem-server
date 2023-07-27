from django.contrib import admin

from .models import CirclePlan


@admin.register(CirclePlan)
class CirclePlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "published",
        "display_date",
        "created_by",
    )
    list_filter = ("date_created",)
    search_fields = ("name",)
