from urllib.parse import urljoin

from django.conf import settings
from django.contrib import admin
from django.utils.safestring import mark_safe as safe

from .models import Redirect


@admin.register(Redirect)
class RedirectAdmin(admin.ModelAdmin):
    list_display = ("url", "slug", "count")
    ordering = ("url",)
    readonly_fields = ("count", "get_absolute_url", "generate_qr_code")

    def generate_qr_code(self, obj):
        full_url = urljoin(settings.EMAIL_BASE_URL, obj.get_absolute_url())
        link = f"""https://quickchart.io/qr?text={full_url}&size=500&margin=1"""
        return safe(f'<a target="_blank" href="{link}">Get QR Code</a>')
