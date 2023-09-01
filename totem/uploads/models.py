from django.db import models

# Create your models here.
from totem.utils.models import BaseModel


class Image(BaseModel):
    image = models.ImageField(upload_to="images", blank=True, null=True)
    title = models.CharField(max_length=255)

    def __str__(self):
        return self.image.url
