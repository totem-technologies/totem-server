from django.contrib import admin

from .models import BlogPost


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ("title", "author", "slug", "date_published")
    search_fields = ("title", "subtitle", "content")
    autocomplete_fields = ["author"]

    fieldsets = (
        (
            "Header",
            {
                "fields": ("author", "title", "subtitle", "header_image", "publish", "date_published"),
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
