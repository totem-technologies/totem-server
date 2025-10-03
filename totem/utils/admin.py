import csv

from django.contrib import admin
from django.contrib.admin.models import DELETION, LogEntry
from django.db.models.query import QuerySet
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

admin.site.site_header = "✨ Totem Admin ✨"


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    date_hierarchy = "action_time"

    list_filter = ["user", "content_type", "action_flag"]

    search_fields = ["object_repr", "change_message"]

    list_display = [
        "action_time",
        "user",
        "content_type",
        "object_link",
        "action_flag",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser  # type: ignore

    def object_link(self, obj):
        if obj.action_flag == DELETION:
            link = escape(obj.object_repr)
        else:
            ct = obj.content_type
            link = '<a href="{}">{}</a>'.format(
                reverse(f"admin:{ct.app_label}_{ct.model}_change", args=[obj.object_id]),
                escape(obj.object_repr),
            )
        return mark_safe(link)

    object_link.admin_order_field = "object_repr"  # type: ignore
    object_link.short_description = "object"  # type: ignore


class ExportCsvMixin:
    csv_fields: list | None = None

    def export_as_csv(self, request: HttpRequest, queryset: QuerySet):
        meta = queryset.model._meta
        field_names = self.csv_fields or [field.name for field in meta.fields]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename={}.csv".format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Export Selected"  # type: ignore
