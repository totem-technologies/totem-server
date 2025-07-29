from django.contrib import admin
from django.db.models import Q

from totem.utils.admin import ExportCsvMixin

from .models import OnboardModel


class HasHopesFilter(admin.SimpleListFilter):
    title = "Has Hopes"  # Display name
    parameter_name = "has_hopes"  # URL parameter

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(hopes__isnull=True).exclude(hopes="")
        if self.value() == "no":
            return queryset.filter(Q(hopes__isnull=True) | Q(hopes=""))


@admin.register(OnboardModel)
class OnboardAdmin(ExportCsvMixin, admin.ModelAdmin):
    actions = ["export_as_csv"]
    list_display = ["user", "onboarded", "created", "updated"]
    search_fields = ["user__email"]
    list_filter = (
        "created",
        "updated",
        "onboarded",
        HasHopesFilter,
    )
    readonly_fields = ("user_name",)
