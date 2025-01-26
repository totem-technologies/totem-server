from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from django.utils import timezone

from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import AdminURLMixin, SluggedModel

User = get_user_model()


class BlogPost(AdminURLMixin, MarkdownMixin, SluggedModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=2000, blank=True)
    author = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name="blog_posts", help_text="Author of the blog post", null=True
    )
    header_image = models.ImageField(
        upload_to="blog/headers/%Y/%m/%d/", blank=True, help_text="Header image for blog post (PNG, JPG, max 5MB)"
    )
    content = MarkdownField(
        help_text="Markdown content for the blog post. Do not use h1 (single #) headers.",
    )
    date_published = models.DateTimeField(default=timezone.now)
    publish = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        self.validate_markdown(self.content)  # Add markdown validation

    def get_absolute_url(self) -> str:
        return reverse("blog:detail", kwargs={"slug": self.slug})

    class Meta:  # type: ignore
        ordering = ["-date_published"]
