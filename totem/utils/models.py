import random
import string

from django.db import models


def make_slug():
    return "".join(
        random.sample(string.ascii_lowercase, 3)
        + random.sample(string.digits, 3)
        + random.sample(string.ascii_lowercase, 3)
    )


class BaseModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SluggedModel(BaseModel):
    slug = models.SlugField(db_index=True, unique=True, editable=False, blank=True, default=make_slug)

    def save(self, *args, **kwargs):
        while not self.slug:
            newslug = "".join(
                random.sample(string.ascii_lowercase, 3)
                + random.sample(string.digits, 3)
                + random.sample(string.ascii_lowercase, 3)
            )

            if not self.__class__.objects.filter(slug=newslug).exists():
                self.slug = newslug

        super().save(*args, **kwargs)

    class Meta:
        abstract = True
