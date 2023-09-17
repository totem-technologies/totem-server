from django.db import models
from django.urls import reverse

from totem.utils.models import SluggedModel


class Redirect(SluggedModel):
    url = models.CharField()
    permanent = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    count = models.BigIntegerField(default=0)

    def __str__(self):
        return self.url

    def get_absolute_url(self):
        return reverse("pages:redirect", kwargs={"slug": self.slug})

    class Meta:
        verbose_name = "Redirect"
        verbose_name_plural = "Redirects"
        ordering = ["url"]
        indexes = [models.Index(fields=["url"])]
        constraints = [
            models.UniqueConstraint(fields=["url"], name="unique_redirect_url"),
            models.UniqueConstraint(fields=["slug"], name="unique_redirect_slug"),
        ]

    def increment_count(self):
        self.count += 1
        self.save()
