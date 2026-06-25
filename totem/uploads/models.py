from django.db import models
from imagekit import ImageSpec
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFit, Transpose

# Create your models here.
from totem.utils.images import ConvertToSRGB
from totem.utils.models import SluggedModel


class TotemImageSpec(ImageSpec):
    # Bake in EXIF orientation and convert any wide-gamut (Display P3) profile to sRGB
    # before resizing (which drops both tags).
    processors = [Transpose(), ConvertToSRGB(), ResizeToFit(1500, 1500)]
    format = "WEBP"
    # method=5: near-best WEBP compression search for a fraction of method=6's encode time.
    options = {"quality": 80, "method": 5}


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
