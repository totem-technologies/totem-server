from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe as safe

from .models import Redirect


@admin.register(Redirect)
class RedirectAdmin(admin.ModelAdmin):
    list_display = ("url", "slug", "count")
    ordering = ("url",)
    readonly_fields = ("count", "get_absolute_url", "generate_qr_code")

    def generate_qr_code(self, obj):
        link = reverse("pages:redirect_qr", kwargs={"slug": obj.slug})
        return safe(f'<a target="_blank" href="{link}">Get QR Code</a>')
