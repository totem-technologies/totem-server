import logging
import os
from typing import final

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .models import Image


def filename_to_title(filename: str) -> str:
    """Convert a filename to title case, removing extension."""
    # Remove file extension
    name_without_ext = os.path.splitext(filename)[0]

    # Replace common separators with spaces
    name = name_without_ext.replace("_", " ").replace("-", " ")

    # Convert to title case
    return name.title()


@final
class ImageAdminForm(forms.ModelForm):
    class Meta:
        model = Image
        fields = ["title", "image"]

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image and not self.instance.pk:
            # Only require image when creating a new record
            raise ValidationError("Please select an image file to upload.")
        return image


@final
@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    form = ImageAdminForm
    list_display = ("title", "thumbnail_preview", "slug", "date_created")
    search_fields = ("title", "slug")
    list_filter = ("date_created",)
    fields = ["title", "image", "slug", "markdown_code", "image_tag", "date_created", "date_modified"]
    readonly_fields = ("date_created", "date_modified", "image_tag", "slug", "markdown_code")
    ordering = ("-date_created",)
    date_hierarchy = "date_created"
    list_per_page = 20
    list_max_show_all = 200
    save_on_top = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "bulk-upload/",
                self.admin_site.admin_view(self.bulk_upload_view),
                name="uploads_image_bulk_upload",
            ),
            path(
                "bulk-upload-ajax/",
                self.admin_site.admin_view(self.bulk_upload_ajax),
                name="uploads_image_bulk_upload_ajax",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["bulk_upload_url"] = reverse("admin:uploads_image_bulk_upload")
        return super().changelist_view(request, extra_context)

    def bulk_upload_view(self, request):
        """Display the bulk upload interface."""
        if request.method == "GET":
            context = {
                "site_header": self.admin_site.site_header,
                "site_title": self.admin_site.site_title,
                "title": "Bulk Image Upload",
                "opts": self.model._meta,
                "has_view_permission": self.has_view_permission(request),
            }
            return render(request, "admin/uploads/bulk_upload.html", context)

    def bulk_upload_ajax(self, request):
        """Handle individual file upload via AJAX."""
        if request.method != "POST":
            return JsonResponse({"error": "Only POST requests allowed"}, status=405)

        if "image" not in request.FILES:
            return JsonResponse({"error": "No image file provided"}, status=400)

        image_file = request.FILES["image"]

        # Generate title from filename
        title = filename_to_title(image_file.name)

        try:
            # Create the image instance
            image = Image(title=title, image=image_file)
            image.save()

            return JsonResponse(
                {
                    "success": True,
                    "title": image.title,
                    "url": image.image.url,
                    "admin_url": reverse("admin:uploads_image_change", args=[image.pk]),
                }
            )
        except Exception:
            logging.error("Error occurred while saving image", exc_info=True)
            return JsonResponse({"error": "A server error has occurred"}, status=500)

    def image_tag(self, obj: Image):
        if obj and obj.image:
            return mark_safe(
                f'<a href="{escape(obj.image.url)}" target="_blank">'
                f'<img title="{escape(obj.title)}" src="{escape(obj.image.url)}" '
                f'style="max-width: 500px; max-height: 500px;" />'
                f"</a>"
            )
        return "No image uploaded yet."

    def markdown_code(self, obj: Image):
        code = f'{{% image slug="{obj.slug}" %}}'
        return mark_safe(
            f'<a href="#" style="text-decoration: underline; color: #0066cc;" '
            f'onclick="event.preventDefault(); '
            f"navigator.clipboard.writeText('{escape(code)}').then(() => {{ "
            f"const originalText = this.innerHTML; "
            f"this.innerHTML = 'Copied!'; "
            f"setTimeout(() => {{ this.innerHTML = originalText; }}, 1500); "
            f"}}).catch(err => console.error('Failed to copy:', err)); return false;\">"
            f"<code>{escape(code)}</code></a> "
            f'<span style="color: #666; font-size: 0.9em;">(Click to copy)</span>'
        )

    def thumbnail_preview(self, obj: Image):
        if obj and obj.image:
            # Link to the change page rather than the raw image
            change_url = reverse("admin:uploads_image_change", args=(obj.pk,))
            return mark_safe(
                f'<a href="{change_url}">'
                f'<img src="{escape(obj.image.url)}" width="100" height="auto" '
                f'style="object-fit: contain;" />'
                f"</a>"
            )
        return "No image"

    thumbnail_preview.short_description = "Preview"  # pyright: ignore[reportFunctionMemberAccess]
    image_tag.short_description = "Image Preview"  # pyright: ignore[reportFunctionMemberAccess]
    markdown_code.short_description = "Markdown Code"  # pyright: ignore[reportFunctionMemberAccess]
