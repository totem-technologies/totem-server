from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _
from impersonate.admin import UserAdminImpersonateMixin

from totem.users.forms import UserAdminChangeForm, UserAdminCreationForm

from .models import Feedback, KeeperProfile, User


@admin.register(User)
class UserAdmin(UserAdminImpersonateMixin, auth_admin.UserAdmin):
    open_new_window = True
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("name", "profile_image", "profile_avatar_type", "timezone")}),
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
    list_display = ["email", "name", "verified", "date_joined"]
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
