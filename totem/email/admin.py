from django.contrib import admin

from .models import EmailLog, SubscribedModel


@admin.register(SubscribedModel)
class SubscribedModelAdmin(admin.ModelAdmin):
    list_display = ["user", "user", "subscribed", "created"]


@admin.action(description="Clear out email logs older than 30 days")
def clear_logs(modeladmin, request, queryset):
    EmailLog.clear_old()


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["recipient", "subject", "template", "created"]
    list_filter = ["template"]
    readonly_fields = [field.name for field in EmailLog._meta.get_fields()]
    actions = [clear_logs]
