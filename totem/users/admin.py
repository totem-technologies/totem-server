from auditlog.admin import LogEntryAdmin
from auditlog.models import LogEntry
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from impersonate.admin import UserAdminImpersonateMixin

from totem.users.forms import UserAdminChangeForm, UserAdminCreationForm
from totem.utils.admin import ExportCsvMixin

from .models import Feedback, KeeperProfile, User


@admin.register(User)
class UserAdmin(UserAdminImpersonateMixin, ExportCsvMixin, auth_admin.UserAdmin):
    actions = ["export_as_csv"]
    open_new_window = True
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {"fields": ("name", "profile_image", "profile_avatar_type", "timezone", "newsletter_consent")},
        ),
        (
            _("Fixed PIN for App Store Review. DANGER."),
            {"fields": ("fixed_pin", "fixed_pin_enabled")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_display = ["email", "name", "verified", "newsletter_consent", "date_joined"]
    list_filter = ["is_active", "is_staff", "is_superuser", "verified", "newsletter_consent", "fixed_pin_enabled"]
    search_fields = ["name", "email"]
    ordering = ["email"]
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Other admins ask this when rendering user relation widgets (attendees,
        # author, etc.) to decide whether to show a "+" create-user button, which
        # confuses staff. Only allow adding users from the User admin itself.
        match = request.resolver_match
        if match is None or not (match.url_name or "").startswith("users_user_"):
            return False
        return super().has_add_permission(request)


@admin.register(KeeperProfile)
class KeeperProfileAdmin(admin.ModelAdmin):
    autocomplete_fields = ("user",)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    pass


# Create a custom auitlog admin to remove the first_name field from the search
# Unregister the default LogEntryAdmin
admin.site.unregister(LogEntry)


# Create a subclass of LogEntryAdmin with modified search_fields
class CustomLogEntryAdmin(LogEntryAdmin):
    search_fields = [
        "timestamp",
        "object_repr",
        "changes",
        "actor__name",
        "actor__email",
        "actor__slug",
    ]


# Register your customized version
admin.site.register(LogEntry, CustomLogEntryAdmin)
