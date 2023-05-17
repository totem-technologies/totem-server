from django.contrib import admin

from .models import CoursePage


@admin.register(CoursePage)
class CoursePageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "slug",
        "created_by",
    )
    list_filter = ("date_created", "created_by")
    search_fields = ("title", "slug")
