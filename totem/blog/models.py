from django.db import models

from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import AdminURLMixin, SluggedModel


class BlogPost(AdminURLMixin, MarkdownMixin, SluggedModel):
    title = models.CharField(max_length=255)
    header_image = models.ImageField(
        upload_to="blog/headers/%Y/%m/%d/", blank=True, help_text="Header image for blog post (PNG, JPG, max 5MB)"
    )
    content = MarkdownField(
        help_text="Markdown content for the blog post",
    )
    date_published = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        self.validate_markdown(self.content)  # Add markdown validation

    class Meta:
        ordering = ["-date_published"]
