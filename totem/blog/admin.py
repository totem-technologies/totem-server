from django.contrib import admin
from django.utils.safestring import mark_safe
from django import forms
from totem.users.models import User

from .models import BlogPost


class AuthorDropdownFilter(admin.SimpleListFilter):
    template = "admin/dropdown_filter.html"
    parameter_name = "author"
    title = "Author"

    def lookups(self, request, model_admin):
        return User.objects.filter(keeper_profile__isnull=False).values_list("slug", "name")

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(author__slug=self.value())
        return queryset


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    save_on_top = True
    list_display = ("title", "author__email", "get_header_image", "date_published", "publish")
    list_filter = [AuthorDropdownFilter]
    search_fields = ("title", "subtitle", "content")
    autocomplete_fields = ["author"]
    readonly_fields = ["read_time"]

    def get_header_image(self, obj):
        if obj.header_image:
            return mark_safe(f'<img src="{obj.header_image.url}" height="50" />')
        return "-"

    get_header_image.short_description = "Header Image"  # type: ignore  # pyright: ignore[reportFunctionMemberAccess]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        form.base_fields["author"].initial = request.user  # type: ignore
        form.base_fields["summary"].widget = forms.Textarea(attrs={"rows": 3})
        return form

    fieldsets = (
        (
            "Header",
            {
                "fields": (
                    "author",
                    "title",
                    "subtitle",
                    "summary",
                    "header_image",
                    "date_published",
                    "read_time",
                    "publish",
                ),
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
