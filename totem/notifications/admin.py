from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import FCMDevice


@admin.register(FCMDevice)
class FCMDeviceAdmin(admin.ModelAdmin):
    list_display = ("user__email", "token_truncated", "active", "last_used", "created_at")
    list_filter = ("active", "created_at", "updated_at", "last_used")
    search_fields = ("user__username", "user__email", "token")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user",)

    fieldsets = (
        (None, {"fields": ("user", "token", "active")}),
        (_("Timestamps"), {"fields": ("last_used", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def token_truncated(self, obj):
        """Display a truncated version of the token for readability"""
        if obj.token:
            return f"{obj.token[:15]}..."
        return "-"

    token_truncated.short_description = _("Token")
