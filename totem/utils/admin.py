import csv
import logging
from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.contrib.admin.models import DELETION, LogEntry
from django.db.models.query import QuerySet
from django.forms import CharField, HiddenInput
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)

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


STALE_DATA_HIDDEN_FIELD = "_loaded_at"
STALE_DATA_ERROR = (
    "This record was modified while you were editing it. "
    "Your changes have NOT been saved. Please copy any changes you made, "
    "refresh the page, and try again."
)


def _make_stale_check_form(check_field: str):
    """Create a ModelForm subclass with a hidden timestamp field for stale data detection.

    Declaring the field on the class (rather than adding it in __init__) ensures
    modelform_factory recognizes it, so it works in fieldsets without custom templates.
    """
    from django.core.exceptions import ValidationError
    from django.forms import ModelForm

    class StaleCheckForm(ModelForm):
        _loaded_at = CharField(widget=HiddenInput, required=False)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance and self.instance.pk:
                ts = getattr(self.instance, check_field, None)
                self.fields[STALE_DATA_HIDDEN_FIELD].initial = str(ts.timestamp()) if ts else ""

        def clean(self):
            cleaned = super().clean()
            if not cleaned:
                return cleaned

            if not self.instance or not self.instance.pk:
                return cleaned

            loaded_at_str = cleaned.get(STALE_DATA_HIDDEN_FIELD, "")
            if not loaded_at_str:
                return cleaned

            current_ts = type(self.instance).objects.values_list(check_field, flat=True).get(pk=self.instance.pk)
            if current_ts and str(current_ts.timestamp()) != loaded_at_str:
                logger.warning(
                    "Stale data rejected for %s pk=%s (loaded: %s, current: %s)",
                    type(self.instance).__name__,
                    self.instance.pk,
                    loaded_at_str,
                    current_ts.timestamp(),
                )
                raise ValidationError(STALE_DATA_ERROR)

            return cleaned

    return StaleCheckForm


if TYPE_CHECKING:
    from django.contrib.admin.options import BaseModelAdmin as _StaleCheckBase
else:
    _StaleCheckBase = object


class StaleDataCheckAdminMixin(_StaleCheckBase):
    """Admin mixin that prevents saving over data modified since the form was loaded.

    Uses the model's date_modified timestamp for optimistic locking. If the record
    was changed between page load and save, the save is rejected with an error message.

    Works for both ModelAdmin and InlineModelAdmin. The model must have a
    date_modified field (e.g. via BaseModel).

    The hidden timestamp field is declared on the form class so modelform_factory
    recognizes it, and injected into the first fieldset so Django renders it
    automatically as a hidden row — no custom templates needed.

    Usage:
        class MyAdmin(StaleDataCheckAdminMixin, admin.ModelAdmin):
            ...

        class MyInline(StaleDataCheckAdminMixin, admin.StackedInline):
            ...
    """

    stale_check_field: str = "date_modified"

    def get_fieldsets(self, request: HttpRequest, obj: Any = None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if fieldsets:
            first_name, first_options = fieldsets[0]
            fields = list(first_options.get("fields", []))
            if STALE_DATA_HIDDEN_FIELD not in fields:
                fields.append(STALE_DATA_HIDDEN_FIELD)
                fieldsets[0] = (first_name, {**first_options, "fields": fields})
        return fieldsets

    def get_form(self, request: HttpRequest, obj: Any = None, change=False, **kwargs) -> Any:
        kwargs.setdefault("form", _make_stale_check_form(self.stale_check_field))
        return super().get_form(request, obj, **kwargs)  # pyright: ignore[reportAttributeAccessIssue]

    def get_formset(self, request: HttpRequest, obj: Any = None, **kwargs) -> Any:
        kwargs.setdefault("form", _make_stale_check_form(self.stale_check_field))
        return super().get_formset(request, obj, **kwargs)  # pyright: ignore[reportAttributeAccessIssue]


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
