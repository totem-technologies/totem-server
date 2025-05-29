from django.contrib import admin
from django import forms
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, path
from django.utils.translation import gettext_lazy as _
from django.db.models import QuerySet

from .models import FCMDevice
from .services import send_notification


class FCMMessageForm(forms.Form):
    """Form for sending FCM messages to devices."""

    title = forms.CharField(max_length=255, required=True, help_text=_("Notification title"))
    body = forms.CharField(widget=forms.widgets.Textarea, required=True, help_text=_("Notification body"))


@admin.register(FCMDevice)
class FCMDeviceAdmin(admin.ModelAdmin):
    list_display = ("user__email", "token_truncated", "active", "last_used", "created_at")
    list_filter = ("active", "created_at", "updated_at", "last_used")
    search_fields = ("user__username", "user__email", "token")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user",)
    actions = ["send_fcm_message_action"]

    fieldsets = (
        (None, {"fields": ("user", "token", "active")}),
        (_("Timestamps"), {"fields": ("last_used", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def token_truncated(self, obj):
        """Display a truncated version of the token for readability"""
        if obj.token:
            return f"{obj.token[:15]}..."
        return "-"

    token_truncated.short_description = _("Token")  # type: ignore

    @admin.action(description="Send FCM message to selected devices")
    def send_fcm_message_action(self, request, queryset: QuerySet):
        """Admin action to redirect to the message sending view with selected device IDs."""
        # Filter only active devices
        active_devices = queryset.filter(active=True)

        if not active_devices.exists():
            self.message_user(request, _("No active devices selected."), level=messages.ERROR)
            return

        # Get the IDs of active devices
        selected_ids = ",".join(str(pk) for pk in active_devices.values_list("pk", flat=True))

        # Redirect to the custom view
        url = reverse("admin:notifications_fcmdevice_send_message")
        return HttpResponseRedirect(f"{url}?ids={selected_ids}")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "send-message/",
                self.admin_site.admin_view(self.send_fcm_message_view),
                name="notifications_fcmdevice_send_message",
            ),
        ]
        return custom_urls + urls

    def send_fcm_message_view(self, request):
        """View for sending FCM messages to selected devices."""
        # Get selected device IDs from query parameters
        selected_ids = request.GET.get("ids", "")

        # Split and convert to integers
        try:
            id_list = [int(pk) for pk in selected_ids.split(",")]
            queryset = FCMDevice.objects.filter(pk__in=id_list, active=True)
        except ValueError:
            queryset = FCMDevice.objects.none()

        if not queryset.exists():
            self.message_user(request, _("No active devices found."), level=messages.ERROR)
            return HttpResponseRedirect(reverse("admin:notifications_fcmdevice_changelist"))

        if request.method == "POST":
            form = FCMMessageForm(request.POST)
            if form.is_valid():
                title = form.cleaned_data["title"]
                body = form.cleaned_data["body"]
                tokens = list(queryset.values_list("token", flat=True))
                success = send_notification(tokens, title, body)

                if success:
                    count = len(tokens)
                    self.message_user(
                        request, _("FCM message successfully sent to %(count)d device(s).") % {"count": count}
                    )
                else:
                    self.message_user(request, _("Failed to send FCM message."), level=messages.ERROR)

                return HttpResponseRedirect(reverse("admin:notifications_fcmdevice_changelist"))
        else:
            form = FCMMessageForm()

        return render(
            request,
            "admin/send_fcm_message.html",
            {
                "devices": queryset,
                "form": form,
                "title": _("Send FCM Message"),
            },
        )
