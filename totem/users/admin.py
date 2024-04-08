from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _
from impersonate.admin import UserAdminImpersonateMixin

from totem.users.forms import UserAdminChangeForm, UserAdminCreationForm
from totem.utils.admin import ExportCsvMixin

from .models import Feedback, KeeperProfile, User


class IsOnboardedFilter(admin.SimpleListFilter):
    title = "Onboarded"  # Title for the filter
    parameter_name = "is_onboarded"  # Parameter used in the URL

    def lookups(self, request, model_admin):
        # Choices for the filter
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "yes":
            return queryset.exclude(onboard__isnull=True)
        elif value == "no":
            return queryset.filter(onboard__isnull=True)
        return queryset  # Return unmodified queryset if no filter is selected


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
    list_display = ["email", "name", "verified", "is_onboarded", "newsletter_consent", "date_joined"]
    list_filter = ["is_active", "is_staff", "is_superuser", "verified", "newsletter_consent", IsOnboardedFilter]
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


@admin.register(KeeperProfile)
class KeeperProfileAdmin(admin.ModelAdmin):
    autocomplete_fields = ("user",)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    pass
