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
        help_text="""Markdown content for the blog post. Do not use h1 (single #) headers.
        Add inline images like {% image slug="vji504tvi" %}, after uploading them in the Images section.""",
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
