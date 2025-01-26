from django.db import models
from imagekit import ImageSpec
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFit

# Create your models here.
from totem.utils.models import SluggedModel


class TotemImageSpec(ImageSpec):
    processors = [ResizeToFit(1500, 1500)]
    format = "JPEG"
    options = {"quality": 80, "optimize": True}


def upload_to_id_image(instance, filename: str):
    extension = filename.split(".")[-1]
    return f"images/{instance.slug}.{extension}"


class Image(SluggedModel):
    image = ProcessedImageField(
        null=True,
        blank=True,
        upload_to=upload_to_id_image,
        spec=TotemImageSpec,  # type: ignore
        help_text="Image for content, must be under 5mb",
    )
    title = models.CharField(max_length=255)

    def __str__(self):
        return self.image.url
