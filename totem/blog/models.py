import time

from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from django.utils import timezone
from imagekit import ImageSpec
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFit

from totem.utils.hash import basic_hash
from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import AdminURLMixin, SluggedModel

User = get_user_model()


class BlogImageSpec(ImageSpec):
    processors = [ResizeToFit(1500, 1500)]
    format = "JPEG"
    options = {"quality": 80, "optimize": True}


def upload_to_id_image(instance, filename: str):
    extension = filename.split(".")[-1]
    epoch_time = int(time.time())
    new_filename = basic_hash(f"{filename}-{epoch_time}")
    return f"blog/headers/{new_filename}.{extension}"


class BlogPost(AdminURLMixin, MarkdownMixin, SluggedModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=2000, blank=True)
    summary = models.CharField(
        max_length=2000,
        blank=True,
        help_text="Short summary of the blog post to show in list pages. No Markdown allowed. Max 2000 characters.",
    )
    author = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name="blog_posts", help_text="Author of the blog post", null=True
    )
    header_image = ProcessedImageField(
        blank=True,
        upload_to=upload_to_id_image,
        spec=BlogImageSpec,  # type: ignore
        help_text="Image for the blog header, must be under 5mb",
    )
    content = MarkdownField(
        max_length=20000,
        help_text="""Markdown content for the blog post. Do not use h1 (single #) headers.
        Add inline images like {% image slug="vji504tvi" %}, after uploading them in the Images section.""",
    )
    date_published = models.DateTimeField(default=timezone.now)
    publish = models.BooleanField(default=False)
    read_time = models.PositiveIntegerField(default=1, help_text="Estimated reading time in minutes (auto-calculated)")

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        self.validate_markdown(self.content)  # Add markdown validation

    def calculate_read_time(self):
        """Calculate estimated reading time based on content."""
        # Strip markdown formatting and HTML tags for accurate word count

        # Remove markdown formatting
        text = self.content
        text = text.replace("#", "")
        text = text.replace("-", "")
        text = text.replace("*", "")
        text = text.replace("`", "")
        text = text.replace("<", "")
        text = text.replace(">", "")
        text = text.replace("|", "")
        text = text.replace("{", "")
        text = text.replace("%", "")
        text = text.replace("}", "")

        # Count words
        words = len(text.split())

        # Calculate read time (average reading speed: 225 words per minute)
        # Minimum 1 minute
        read_time = max(1, round(words / 225))

        return read_time

    def save(self, *args, **kwargs):
        """Override save to auto-calculate read_time."""
        self.read_time = self.calculate_read_time()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:detail", kwargs={"slug": self.slug})

    class Meta:  # type: ignore  # pyright: ignore[reportIncompatibleVariableOverride]
        ordering = ["-date_published"]
