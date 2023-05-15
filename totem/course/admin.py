from django.contrib import admin

from .models import CircleScript, Course


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "created_by",
    )
    list_filter = ("date_created", "created_by")
    search_fields = ("title",)


@admin.register(CircleScript)
class CircleScriptAdmin(admin.ModelAdmin):
    pass
