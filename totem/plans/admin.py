from django.contrib import admin

from .models import CirclePlan


@admin.register(CirclePlan)
class CirclePlanAdmin(admin.ModelAdmin):
    list_display = (
        "published",
        "id",
        "name",
        "short_description",
        "display_date",
        "created_by",
    )
    list_filter = ("date_created", "created_by")
    search_fields = ("name",)
