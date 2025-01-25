from django.db import models
from totem.utils.models import SluggedModel, AdminURLMixin
from totem.utils.md import MarkdownMixin

class BlogPost(SluggedModel, AdminURLMixin, MarkdownMixin):
    title = models.CharField(max_length=255)
    header_image = models.ImageField(
        upload_to="blog/headers/%Y/%m/%d/",
        blank=True,
        help_text="Header image for blog post (PNG, JPG, max 5MB)"
    )
    content = models.TextField(
        help_text="Markdown content for the blog post",
    )
    date_published = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-date_published"]
