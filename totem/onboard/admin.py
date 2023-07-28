from django.contrib import admin

from .models import OnboardModel


@admin.register(OnboardModel)
class OnboardAdmin(admin.ModelAdmin):
    list_display = ["user", "onboarded", "created", "updated"]
    list_filter = ("created", "updated")
    readonly_fields = ("user_name",)
