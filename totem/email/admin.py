from django.contrib import admin

from .models import SubscribedModel


@admin.register(SubscribedModel)
class SubscribedModelAdmin(admin.ModelAdmin):
    list_display = ["user", "user", "subscribed", "created"]
