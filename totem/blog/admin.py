from django.contrib import admin
from django.utils.safestring import mark_safe

from .models import BlogPost


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ("title", "header_image_preview", "slug", "date_published")
    search_fields = ("title", "content")
    # prepopulated_fields = {"slug": ("title",)}

    def header_image_preview(self, obj):
        if obj.header_image:
            return mark_safe(f'<img src="{obj.header_image.url}" style="max-height: 50px; max-width: 100px;" />')
        return "-"

    header_image_preview.short_description = "Header Preview"

    fieldsets = (
        (
            "Header",
            {
                "fields": ("title", "header_image"),
            },
        ),
        (
            "Content",
            {
                "fields": ("content",),
                "classes": ("wide",),
            },
        ),
    )
