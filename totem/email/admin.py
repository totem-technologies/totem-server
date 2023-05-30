from django.contrib import admin

from .models import WaitList


@admin.register(WaitList)
class WaitListAdmin(admin.ModelAdmin):
    list_display = ["email", "name", "subscribed", "date_created"]
