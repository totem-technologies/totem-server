from django.contrib import admin

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
class BlogPostAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ("title", "author", "slug", "date_published")
    list_filter = [AuthorDropdownFilter]
    search_fields = ("title", "subtitle", "content")
    autocomplete_fields = ["author"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        form.base_fields["author"].initial = request.user  # type: ignore
        return form

    fieldsets = (
        (
            "Header",
            {
                "fields": ("author", "title", "subtitle", "header_image", "date_published", "publish"),
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
