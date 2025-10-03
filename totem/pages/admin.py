from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe as safe

from .models import Redirect


@admin.register(Redirect)
class RedirectAdmin(admin.ModelAdmin):
    list_display = ("url", "slug", "count", "notes")
    ordering = ("url",)
    readonly_fields = ("count", "absolute_url", "alternate_url", "generate_qr_code")

    def absolute_url(self, obj):
        return safe(f'<a target="_blank" href="{obj.full_url()}">{obj.full_url()}</a>')

    def alternate_url(self, obj):
        return safe(f'<a target="_blank" href="{obj.full_alternate_url()}">{obj.full_alternate_url()}</a>')

    def generate_qr_code(self, obj):
        link = reverse("pages:redirect_qr", kwargs={"slug": obj.slug})
        return safe(f'<a target="_blank" href="{link}">Get QR Code</a>')
