from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse

from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import AdminURLMixin, SluggedModel

User = get_user_model()


class BlogPost(AdminURLMixin, MarkdownMixin, SluggedModel):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blog_posts",
        help_text="Author of the blog post"
    )
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

    def get_absolute_url(self) -> str:
        return reverse("blog:detail", kwargs={"slug": self.slug})

    class Meta:
        ordering = ["-date_published"]
