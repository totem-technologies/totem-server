from urllib.parse import urljoin

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse

from totem.utils.models import SluggedModel


class Redirect(SluggedModel):
    url = models.CharField()
    alternate_slug = models.SlugField(db_index=True, unique=True, null=True, blank=True)
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

    def increment_count(self):
        self.count += 1
        self.save()

    def full_url(self):
        return urljoin(settings.EMAIL_BASE_URL, self.get_absolute_url())

    @classmethod
    def get_by_slug(cls, slug):
        return cls.objects.filter(Q(slug=slug) | Q(alternate_slug=slug)).get()
