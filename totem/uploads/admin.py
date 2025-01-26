from django.contrib import admin
from django.utils.html import escape
from django.utils.safestring import mark_safe

# Register your models here.
from .models import Image


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ("title", "image", "slug")
    search_fields = ("title", "slug")
    list_filter = ("title",)
    fields = ["title", "image"]
    readonly_fields = ["image_tag"]
    ordering = ("-date_created",)
    date_hierarchy = "date_created"
    list_per_page = 20
    list_max_show_all = 200
    readonly_fields = ("date_created", "date_modified")

    def image_tag(self, obj):
        return mark_safe(f'<img title="{escape(obj.title)}"src="{escape(obj.image.url)}" />')

    image_tag.short_description = "Image"
