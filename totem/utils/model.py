import random
import string

from django.db import models


class SluggedModel(models.Model):
    slug = models.SlugField(db_index=True, unique=True, editable=False, blank=True)

    def save(self, *args, **kwargs):
        while not self.slug:
            newslug = "".join(
                random.sample(string.ascii_lowercase, 3)
                + random.sample(string.digits, 3)
                + random.sample(string.ascii_lowercase, 3)
            )

            if not self.objects.filter(pk=newslug).exists():
                self.slug = newslug

        super().save(*args, **kwargs)

    class Meta:
        abstract = True
