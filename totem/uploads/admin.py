from django.contrib import admin
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError
from django import forms
from django.urls import reverse


from .models import Image


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


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    form = ImageAdminForm
    list_display = ("title", "thumbnail_preview", "slug", "date_created")
    search_fields = ("title", "slug")
    list_filter = ("date_created",)
    fields = ["title", "image", "slug", "image_tag", "date_created", "date_modified"]
    readonly_fields = ("date_created", "date_modified", "image_tag", "slug")
    ordering = ("-date_created",)
    date_hierarchy = "date_created"
    list_per_page = 20
    list_max_show_all = 200
    save_on_top = True

    def image_tag(self, obj):
        if obj and obj.image:
            return mark_safe(
                f'<a href="{escape(obj.image.url)}" target="_blank">'
                f'<img title="{escape(obj.title)}" src="{escape(obj.image.url)}" '
                f'style="max-width: 500px; max-height: 500px;" />'
                f"</a>"
            )
        return "No image uploaded yet."

    def thumbnail_preview(self, obj):
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

    thumbnail_preview.short_description = "Preview"  # type: ignore
    image_tag.short_description = "Image Preview"  # type: ignore
